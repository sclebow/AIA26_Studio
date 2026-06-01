"""
Grasshopper Python 3 — update layout schema with any cost/element changes.

Drop this into a Python 3 Script component inside the `compute_room_cost`
cluster. It accepts the layout JSON received from the MCP call (which may
already carry overridden rate_per_m2 values, modified polygons, added/removed
openings, etc.), merges those changes onto a baseline, recomputes every
derived total, and emits the full updated layout JSON.

Inputs (set as item-access on the component):
    json_in         : str   The layout_schema JSON from the MCP request.
    room_name       : str   (optional) Name of the room of interest.
    original_path   : str   (optional) Path to layout_schema-team05.json for
                            sanity merging — only used to back-fill missing
                            keys; never overrides values present in json_in.

Outputs:
    out         : str       Full updated layout JSON.
    summary     : str       Human-readable diff summary.
    total_cost  : float     Project grand total.
    room_total  : float     total_cost of `room_name` (or 0 if not found).
"""

import json
import os
import math


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def polygon_area(poly):
    """Signed-area of a 2D polygon via the shoelace formula. Returns abs area."""
    if not poly or len(poly) < 3:
        return 0.0
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i][0], poly[i][1]
        x2, y2 = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        s += (x1 * y2) - (x2 * y1)
    return abs(s) * 0.5


# ---------------------------------------------------------------------------
# Merge + recompute
# ---------------------------------------------------------------------------

def deep_merge(base, override):
    """Recursively overlay `override` onto a copy of `base`. Lists are replaced."""
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for k, v in override.items():
            result[k] = deep_merge(result.get(k), v) if k in result else v
        return result
    return override if override is not None else base


def recompute_room(room):
    """Refresh area_m2 from polygon (if present) and total_cost from rate."""
    poly = room.get("polygon")
    if poly:
        room["area_m2"] = round(polygon_area(poly), 4)
    rate = room.get("rate_per_m2")
    area = room.get("area_m2")
    if rate is not None and area is not None:
        room["total_cost"] = round(float(rate) * float(area), 2)
    return room


def recompute_layout(layout):
    """Recompute every derived total in the layout in-place."""
    rooms = layout.get("rooms", []) or []
    for r in rooms:
        recompute_room(r)

    openings = layout.get("openings", []) or []
    columns = layout.get("columns", []) or []

    rooms_total = sum(float(r.get("total_cost", 0) or 0) for r in rooms)
    doors_total = sum(float(o.get("cost", 0) or 0) for o in openings if o.get("type") == "door")
    windows_total = sum(float(o.get("cost", 0) or 0) for o in openings if o.get("type") == "window")
    columns_total = sum(float(c.get("cost", 0) or 0) for c in columns)

    grand_total = rooms_total + doors_total + windows_total + columns_total

    layout["summary"] = {
        "rooms_total_cost": round(rooms_total, 2),
        "doors_total_cost": round(doors_total, 2),
        "windows_total_cost": round(windows_total, 2),
        "columns_total_cost": round(columns_total, 2),
        "grand_total": round(grand_total, 2),
        "room_count": len(rooms),
        "door_count": sum(1 for o in openings if o.get("type") == "door"),
        "window_count": sum(1 for o in openings if o.get("type") == "window"),
        "column_count": len(columns),
    }
    return layout


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _load_baseline(path):
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


# Parse incoming JSON
try:
    incoming = json.loads(json_in) if isinstance(json_in, str) else (json_in or {})
except Exception as exc:
    out = json.dumps({"error": "invalid json_in", "detail": str(exc)})
    summary = "ERROR: json_in is not valid JSON"
    total_cost = 0.0
    room_total = 0.0
else:
    baseline = _load_baseline(original_path) or {}
    merged = deep_merge(baseline, incoming) if baseline else incoming
    updated = recompute_layout(merged)

    # Find requested room (if any)
    room_total = 0.0
    matched_room = None
    if room_name:
        target = str(room_name).strip().lower()
        for r in updated.get("rooms", []):
            if str(r.get("name", "")).strip().lower() == target:
                matched_room = r
                room_total = float(r.get("total_cost", 0) or 0)
                break

    out = json.dumps(updated, ensure_ascii=False)
    total_cost = float(updated.get("summary", {}).get("grand_total", 0))

    if matched_room:
        summary = (
            "Updated room: {name}\n"
            "  area_m2     = {area}\n"
            "  rate_per_m2 = {rate}\n"
            "  total_cost  = {total}\n"
            "Project grand_total = {gt}"
        ).format(
            name=matched_room.get("name"),
            area=matched_room.get("area_m2"),
            rate=matched_room.get("rate_per_m2"),
            total=matched_room.get("total_cost"),
            gt=total_cost,
        )
    else:
        summary = "Recomputed full layout. grand_total = {0}".format(total_cost)
