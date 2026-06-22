"""
_edits.py — shared helpers for layout-editing tools.
Fixed: floor material support (reads/writes room.attributes.floorMaterial).
"""

from __future__ import annotations
import json
from typing import Any, Optional

import spatial  # Shapely-backed sound placement (team_02/python is the run root)

MATERIALS = ["carpet", "fabric", "wood", "cork", "plaster", "brick",
             "ceramic", "stone", "concrete", "glass", "metal", "natural"]

# Snap common LLM/user words onto a canonical MATERIALS value (never store a raw unknown).
MATERIAL_SYNONYMS = {
    "timber": "wood", "parquet": "wood", "hardwood": "wood", "oak": "wood",
    "laminate": "wood", "wooden": "wood",
    "granite": "stone", "marble": "stone", "terrazzo": "stone",
    "tile": "ceramic", "tiles": "ceramic", "porcelain": "ceramic", "tiled": "ceramic",
    "rug": "fabric", "textile": "fabric", "upholstery": "fabric", "felt": "fabric",
    "linoleum": "cork", "vinyl": "cork",
}

# Soft / flat furnishings (used for the default material + the acoustic-absorption credit).
CURTAIN_TYPES = {"curtain", "curtains", "blind", "blinds", "drape", "drapes", "shade"}
SOFT_FURNITURE = {"sofa", "bed", "armchair", "rug", "cushion", "couch"} | CURTAIN_TYPES
FURNITURE_TYPES = list(SOFT_FURNITURE) + ["table", "desk", "shelf", "bookshelf",
                                           "cabinet", "dresser", "plant"]
VENT_TYPES = {"natural", "mixed", "mechanical"}

# Realistic small footprints (metres) for sound placement of an added piece.
_FOOTPRINT = {
    "plant": (0.5, 0.5), "rug": (1.6, 2.2), "sofa": (0.9, 2.0), "couch": (0.9, 2.0),
    "armchair": (0.8, 0.8), "cushion": (0.5, 0.5), "table": (0.8, 1.2), "desk": (0.7, 1.4),
    "shelf": (0.35, 1.0), "bookshelf": (0.35, 1.0), "cabinet": (0.5, 1.0),
    "dresser": (0.5, 1.2), "bed": (1.5, 2.0),
}
# Which senses an added element touches (drives the diff's sense_affected + the edit-guide hue).
_ADD_SENSE = {
    "plant": "olfactory+visual", "rug": "tactile+acoustic", "cushion": "tactile+acoustic",
    "curtain": "acoustic+visual", "blind": "acoustic+visual", "drape": "acoustic+visual",
}
_CARDINALS = {"north": "N", "south": "S", "east": "E", "west": "W"}

FLOOR_KEYWORDS = ("floor", "flooring", "ground", "underfoot")
WALL_KEYWORDS  = ("wall", "walls", "partition", "ceiling")


def validate_material(m) -> Optional[str]:
    """Canonicalise an LLM/heuristic material to a known MATERIALS value, or None.
    Keeps an invalid material (an invented finish, a colour, a hex) out of the layout."""
    if not m:
        return None
    raw = str(m).strip().lower()
    if raw in MATERIALS:
        return raw
    if raw in MATERIAL_SYNONYMS:
        return MATERIAL_SYNONYMS[raw]
    for known in MATERIALS:          # substring snap: "warm wood" -> "wood"
        if known in raw:
            return known
    return None


def detect_ventilation(prompt: str) -> Optional[str]:
    p = (prompt or "").lower()
    if any(k in p for k in ("mechanical", "extractor", "extraction", "hvac", "mechanically")):
        return "mechanical"
    if any(k in p for k in ("mixed", "hybrid", "mixed-mode")):
        return "mixed"
    if any(k in p for k in ("natural", "cross vent", "cross-vent", "openable", "fresh air")):
        return "natural"
    return None


def _cardinal_from(text: str) -> Optional[str]:
    t = (text or "").lower()
    for word, card in _CARDINALS.items():
        if word in t:
            return card
    return None


def _match_named(items: list, hint: str) -> Optional[dict]:
    """First item whose name overlaps the hint (substring either way)."""
    h = (hint or "").lower().strip()
    if not h:
        return None
    for it in items:
        name = (it.get("name") or "").lower()
        if name and (name in h or h in name):
            return it
    return None


def load(layout_json_string: str) -> Optional[dict]:
    try:
        return json.loads(layout_json_string)
    except Exception:
        return None


def dump(layout: dict) -> str:
    return json.dumps(layout)


def worst_room_name(scores_json: str) -> Optional[str]:
    try:
        rooms = json.loads(scores_json).get("rooms", [])
        if not rooms:
            return None
        return min(rooms, key=lambda r: r.get("overallScore", 1.0)).get("roomName")
    except Exception:
        return None


def find_target_room(layout: dict, prompt: str, scores_json: str = "",
                     hint: str = "") -> Optional[dict]:
    """Pick the room the edit applies to: named in prompt > hint > worst-scoring > first."""
    rooms = layout.get("rooms", [])
    if not rooms:
        return None
    p = (prompt or "").lower()
    h = (hint or "").lower()

    # 1. explicit room NAME in the prompt or hint — most specific. Checked BEFORE
    #    roomType so "guest bedroom" matches the Guest Bedroom, not the first room whose
    #    type is "bedroom" (which used to mis-route edits to the Master Bedroom).
    for text in (p, h):
        if not text:
            continue
        for room in rooms:
            name = (room.get("name") or "").lower()
            if name and name in text:
                return room

    # 2. room TYPE in the prompt or hint — less specific, only if no name matched.
    for text in (p, h):
        if not text:
            continue
        for room in rooms:
            rtype = (room.get("attributes", {}).get("roomType") or "").lower()
            if rtype and rtype in text:
                return room

    # 3. worst-scoring room
    worst = worst_room_name(scores_json)
    if worst:
        for room in rooms:
            if (room.get("name") or "") == worst:
                return room

    return rooms[0]


def detect_material(prompt: str, hint: str = "") -> Optional[str]:
    p = (prompt or "").lower()
    # Check hint first (LLM-extracted material)
    if hint:
        for m in MATERIALS:
            if m in hint.lower():
                return m
    for m in MATERIALS:
        if m in p:
            return m
    if "soft" in p or "warm" in p or "cosy" in p or "cozy" in p:
        return "fabric"
    return None


def detect_surface_target(prompt: str) -> str:
    """Return 'floor', 'wall', or 'furniture' based on what the user wants to change."""
    p = (prompt or "").lower()
    if any(k in p for k in FLOOR_KEYWORDS):
        return "floor"
    if any(k in p for k in WALL_KEYWORDS):
        return "wall"
    return "furniture"


def detect_furniture_type(prompt: str) -> str:
    p = (prompt or "").lower()
    for t in FURNITURE_TYPES:
        if t in p:
            return t
    if "green" in p or "biophilic" in p:
        return "plant"
    return "plant"


def centroid(geometry: list) -> tuple[float, float]:
    pts = geometry or []
    if pts and len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def next_id(layout: dict, key: str, prefix: str) -> str:
    """Max existing <prefix>-<n> + 1 — collision-safe across removes (len+1 was not)."""
    maxn = 0
    for el in layout.get(key, []):
        eid = str(el.get("id", ""))
        if eid.startswith(prefix + "-"):
            try:
                maxn = max(maxn, int(eid.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return "{}-{}".format(prefix, maxn + 1)


def _anchor(geom) -> Optional[list]:
    """Centroid/midpoint of an element geometry (a segment or a footprint polygon).
    Drives the edit-guide's focus point so the cue lands ON the changed element.
    Drops a duplicated closing vertex first so a closed ring isn't pulled off-centre
    toward its repeated corner."""
    if not geom:
        return None
    pts = geom
    if len(pts) > 1 and list(pts[0]) == list(pts[-1]):
        pts = pts[:-1]
    try:
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
    except (TypeError, IndexError, ValueError):
        return None
    if not xs:
        return None
    return [round(sum(xs) / len(xs), 3), round(sum(ys) / len(ys), 3)]


def make_layout_diff(room: Optional[dict], attribute: str,
                     old_value: Any, new_value: Any,
                     sense_affected: str,
                     at: Optional[list] = None, el: Optional[list] = None) -> dict:
    """Build the structured diff payload for the frontend.

    Optional `at` (anchor point [x,y]) and `el` (the changed element's geometry —
    a segment or footprint polygon) let the edit-guide focus EXACTLY on the changed
    window/door/furniture. Room-wide edits (floor/wall material, ventilation, glazing)
    omit both; the frontend falls back to the room polygon + centroid."""
    if room is None:
        return {}
    d = {
        "room_id":       room.get("id", ""),
        "room_name":     room.get("name", "unknown"),
        "attribute":     attribute,
        "old_value":     old_value,
        "new_value":     new_value,
        "sense_affected": sense_affected,
    }
    if at is not None:
        d["at"] = at
    if el is not None:
        d["el"] = el
    return d


# ── Pure mutators ─────────────────────────────────────────────────────────────
# The mutation core of each edit, factored OUT of the graph nodes so it can run on
# either the canonical layout (commit path) or a throwaway clone (preview path).
# Each mutates `layout` in place and returns the structured diff — no state, no
# persistence, no flags. The edit nodes wrap these with the state plumbing; the
# preview node calls them on a clone and never persists.

def furniture_material_for(ftype: str) -> str:
    """Default material for an added furniture type (matches add_furniture)."""
    return ("natural" if ftype == "plant" else
            "fabric"  if ftype in SOFT_FURNITURE else "wood")


def resolve_glazing(prompt: str) -> tuple[Optional[str], bool]:
    """Prompt → (glazing_type|None, wants_more_light). Detection only; the mutation
    is apply_modify_glazing. Shared so commit and preview read intent identically."""
    p = (prompt or "").lower()
    gtype = ("triple" if "triple" in p else
             "single" if "single" in p else
             "double" if "double" in p else None)
    wants_more = any(k in p for k in
        ["more light", "bigger", "larger", "brighter", "window", "light", "glazing", "skylight"])
    return gtype, wants_more


def apply_change_material(layout: dict, room: Optional[dict],
                          surface: str, material: str) -> dict:
    """Set floor / wall / furniture material on `layout`. Returns the diff."""
    if surface == "floor" and room:
        attrs   = room.setdefault("attributes", {})
        old_val = attrs.get("floorMaterial", "unset")
        attrs["floorMaterial"] = material
        return make_layout_diff(room, "floorMaterial", old_val, material, "tactile")

    if surface == "wall":
        # Room-SCOPED wall finish (mirrors floorMaterial). The old code rewrote EVERY
        # entry of the sparse global `structure` array — so "change the bedroom walls"
        # silently changed every wall in the flat and didn't move the bedroom's score.
        if not room:
            return {}
        attrs   = room.setdefault("attributes", {})
        old_val = attrs.get("wallMaterial", "unset")
        attrs["wallMaterial"] = material
        return make_layout_diff(room, "wallMaterial", old_val, material, "tactile+acoustic")

    if room:
        rid       = room.get("id")
        changed   = False
        old_val   = material
        furn_geom = None
        for f in layout.get("furniture", []):
            if f.get("attributes", {}).get("roomId") == rid:
                old_val = f.get("attributes", {}).get("material", "unknown")
                f.setdefault("attributes", {})["material"] = material
                changed = True
                if furn_geom is None:
                    furn_geom = f.get("geometry")   # light the (first) changed piece
        return make_layout_diff(
            room, "furnitureMaterial", old_val if changed else "none", material, "tactile",
            at=_anchor(furn_geom) if furn_geom else None,
            el=furn_geom if furn_geom else None,
        )

    return {}


# Realistic footprint VARIANTS (metres), LARGEST → smallest, so a piece can shrink to
# fit a tight room instead of being rejected outright. All within check_layout_geometry's
# plausible size ranges. "Smallest that fits wins" — try the biggest realistic size first
# and step down only when nothing places soundly, so a plant almost always finds a home.
_FOOTPRINT_VARIANTS = {
    "plant":     [(0.7, 0.7), (0.5, 0.5), (0.35, 0.35), (0.25, 0.25)],
    "armchair":  [(0.85, 0.85), (0.7, 0.7), (0.6, 0.6)],
    "table":     [(0.9, 1.2), (0.8, 1.0), (0.6, 0.8)],
    "desk":      [(0.7, 1.4), (0.6, 1.1), (0.5, 0.9)],
    "shelf":     [(0.35, 1.0), (0.3, 0.7), (0.25, 0.5)],
    "bookshelf": [(0.35, 1.0), (0.3, 0.7), (0.25, 0.5)],
    "cabinet":   [(0.5, 1.0), (0.45, 0.8), (0.4, 0.6)],
    "dresser":   [(0.5, 1.2), (0.45, 0.9), (0.45, 0.7)],
}


def _size_variants(ftype: str) -> list:
    """Largest→smallest realistic footprints to try for `ftype`."""
    if ftype in _FOOTPRINT_VARIANTS:
        return _FOOTPRINT_VARIANTS[ftype]
    w, h = _FOOTPRINT.get(ftype, (0.6, 0.6))
    return [(w, h), (round(w * 0.82, 2), round(h * 0.82, 2))]


def _place_sound(layout: dict, room: dict, ftype: str,
                 audit_fn=None, baseline=None) -> tuple:
    """Find a SOUND spot for `ftype` in `room`, trying multiple sizes (largest first) and
    multiple candidate spots. With an `audit_fn` (layout-dict → defect list) it accepts only
    a spot that introduces NO new architectural defect vs `baseline` — so the per-op revert
    gate becomes a no-op for adds and a plant almost always lands somewhere. Without one
    (preview / no gate) it falls back to the single best spot. Returns (ring|None, downsized)."""
    variants = _size_variants(ftype)
    if audit_fn is None:
        w, h = variants[0]
        return spatial.place_furniture(layout, room, w, h), False
    base = set(baseline or [])
    furn = layout.setdefault("furniture", [])
    for vi, (w, h) in enumerate(variants):
        for geo in spatial.place_furniture_candidates(layout, room, w, h):
            probe = {"id": "__probe__", "name": "probe", "geometry": geo,
                     "attributes": {"roomId": room.get("id"), "type": ftype}}
            furn.append(probe)
            new_defects = set(audit_fn(layout)) - base
            furn.pop()
            if not new_defects:
                return geo, (vi > 0)
    return None, False


def apply_add_furniture(layout: dict, room: Optional[dict],
                        ftype: str, material: str,
                        audit_fn=None, baseline=None) -> dict:
    """Append a furniture/plant/curtain element to `room`, placed SOUNDLY (against a
    wall / at the window / centred for a rug — never the dead centre, never in a doorway).
    Tries multiple sizes + spots, audit-checking each when `audit_fn` is given.
    Returns the diff, or {} if no sound spot could be found at any size."""
    if not room:
        return {}
    downsized = False
    if ftype in CURTAIN_TYPES:
        geo = spatial.place_curtain(layout, room)      # hang inside the window wall
    elif ftype == "rug":
        geo = spatial.place_rug(layout, room)          # centred floor covering
    else:
        geo, downsized = _place_sound(layout, room, ftype, audit_fn, baseline)
    if not geo:
        return {}
    new_id = next_id(layout, "furniture", "furn")
    layout.setdefault("furniture", []).append({
        "id": new_id,
        "name": f"Added {ftype}",
        "geometry": geo,
        "attributes": {"roomId": room.get("id"), "type": ftype, "material": material},
    })
    sense = _ADD_SENSE.get(ftype, "tactile")
    label = f"added {'compact ' if downsized else ''}{ftype} ({material})"
    diff = make_layout_diff(room, "furniture", "none", label, sense,
                            at=_anchor(geo), el=geo)
    if downsized:
        diff["downsized"] = True   # transient flag; apply_edits pops it into edit_notes
    return diff


def apply_modify_glazing(layout: dict, room: Optional[dict],
                         gtype: Optional[str], wants_more: bool) -> dict:
    """Raise glazing ratio and/or upgrade glazing type on `room`. Returns the diff."""
    if not room:
        return {}
    attrs  = room.setdefault("attributes", {})
    old_gr = float(attrs.get("glazingRatio", 0.10))
    new_gr = round(max(old_gr, 0.25), 2) if (wants_more or gtype is None) else old_gr
    attrs["glazingRatio"] = new_gr

    applied_gt = gtype or "triple"
    rid      = room.get("id")
    old_gt   = "double"
    win_geom = None
    for win in layout.get("windows", []):
        if win.get("attributes", {}).get("roomId") == rid:
            old_gt = win.get("attributes", {}).get("glazingType", "double")
            win.setdefault("attributes", {})["glazingType"] = applied_gt
            if win_geom is None:
                win_geom = win.get("geometry")   # light the (first) changed window

    return make_layout_diff(
        room, "glazingRatio",
        f"ratio={old_gr:.2f}, type={old_gt}",
        f"ratio={new_gr:.2f}, type={applied_gt}",
        "visual+thermal",
        at=_anchor(win_geom) if win_geom else None,
        el=win_geom if win_geom else None,
    )


def apply_modify_ventilation(layout: dict, room: Optional[dict],
                             vent_type: Optional[str]) -> dict:
    """Set the room's ventilation strategy (natural / mixed / mechanical). Already a
    direct olfactory driver in the scoring model. Returns the diff."""
    if not room:
        return {}
    vt = (vent_type or "").lower()
    if vt not in VENT_TYPES:
        vt = "natural"
    attrs = room.setdefault("attributes", {})
    old = attrs.get("ventilationType", "natural")
    attrs["ventilationType"] = vt
    return make_layout_diff(room, "ventilationType", old, vt, "olfactory")


def apply_add_window(layout: dict, room: Optional[dict],
                     glazing_type: Optional[str] = None) -> dict:
    """Place a new window on a CLEAR exterior wall span (orientation from the wall
    normal) AND raise the room's glazingRatio so visual + thermal actually respond.
    Returns the diff, or {} if there is no clear exterior span."""
    if not room:
        return {}
    spot = spatial.place_window(layout, room)
    if not spot:
        return {}
    gt = glazing_type if glazing_type in ("single", "double", "triple") else "double"
    area = round(spatial._seg_len(spot["geometry"]) * 1.2, 2)
    new_id = next_id(layout, "windows", "window")
    layout.setdefault("windows", []).append({
        "id": new_id,
        "name": f"{room.get('name', 'Room')} {spot['facing']} Window",
        "geometry": spot["geometry"],
        "attributes": {"roomId": room.get("id"), "area": area,
                       "orientation": spot["facing"], "glazingType": gt},
    })
    attrs = room.setdefault("attributes", {})
    old_gr = float(attrs.get("glazingRatio", 0.10))
    new_gr = round(min(0.35, max(old_gr, 0.20)), 2)   # new glazing → visual responds
    attrs["glazingRatio"] = new_gr
    return make_layout_diff(
        room, "window", "none",
        f"added {spot['facing']} window ({gt}); glazing {old_gr:.2f}->{new_gr:.2f}",
        "visual+thermal",
        at=_anchor(spot["geometry"]), el=spot["geometry"],
    )


def apply_move_window(layout: dict, room: Optional[dict], target_hint: str = "") -> dict:
    """Relocate one of the room's windows to a different (or sunnier) exterior wall.
    Honours a named wall in the prompt ("move it to the north wall"). Returns the diff."""
    if not room:
        return {}
    rid = room.get("id")
    wins = [w for w in layout.get("windows", [])
            if w.get("attributes", {}).get("roomId") == rid]
    if not wins:
        return {}
    win = _match_named(wins, target_hint) or wins[0]
    old_orient = win.get("attributes", {}).get("orientation", "?")
    need = spatial._seg_len(win.get("geometry", [])) or spatial.WINDOW_LEN
    facing_pref = _cardinal_from(target_hint)
    # Drop it first so place_window won't treat its own span as occupied.
    layout["windows"] = [w for w in layout.get("windows", []) if w is not win]
    spot = spatial.place_window(layout, room, need=need, facing_pref=facing_pref)
    if not spot:
        layout.setdefault("windows", []).append(win)   # restore — nothing moved
        return {}
    win["geometry"] = spot["geometry"]
    win.setdefault("attributes", {})["orientation"] = spot["facing"]
    layout.setdefault("windows", []).append(win)
    return make_layout_diff(
        room, "windowPosition",
        f"{old_orient} wall", f"{spot['facing']} wall", "visual+thermal",
        at=_anchor(spot["geometry"]), el=spot["geometry"],
    )


def find_furniture(layout: dict, room: Optional[dict], name_or_type: str) -> Optional[dict]:
    """Match a furniture item by name substring, then exact type, then type substring —
    scoped to the room when one is given."""
    key = (name_or_type or "").lower().strip()
    rid = room.get("id") if room else None
    pool = [f for f in layout.get("furniture", [])
            if rid is None or f.get("attributes", {}).get("roomId") == rid]
    if not key:
        return None
    for f in pool:
        if key in (f.get("name", "").lower()):
            return f
    for f in pool:
        if key == (f.get("attributes", {}).get("type", "").lower()):
            return f
    for f in pool:
        if key in (f.get("attributes", {}).get("type", "").lower()):
            return f
    return None


def apply_remove_furniture(layout: dict, room: Optional[dict], name_or_type: str) -> dict:
    """Remove a named/typed furniture item. Removal can only fix geometry, never break
    it, so the audit never reverts this. Returns the diff."""
    f = find_furniture(layout, room, name_or_type)
    if not f:
        return {}
    f_geom = f.get("geometry")
    layout["furniture"] = [x for x in layout.get("furniture", []) if x is not f]
    return make_layout_diff(
        room, "furniture", f.get("name", "item"),
        f"removed {f.get('name', 'item')}", "spatial",
        at=_anchor(f_geom), el=f_geom,
    )


def apply_remove_window(layout: dict, room: Optional[dict], hint: str = "") -> dict:
    """Remove one of the room's windows and lower its glazingRatio so visual + thermal
    respond (not just the per-window thermal term). Returns the diff."""
    if not room:
        return {}
    rid = room.get("id")
    wins = [w for w in layout.get("windows", [])
            if w.get("attributes", {}).get("roomId") == rid]
    if not wins:
        return {}
    win = _match_named(wins, hint) or wins[0]
    win_geom = win.get("geometry")
    layout["windows"] = [w for w in layout.get("windows", []) if w is not win]
    attrs = room.setdefault("attributes", {})
    old_gr = float(attrs.get("glazingRatio", 0.10))
    new_gr = round(max(0.05, old_gr - 0.10), 2)
    attrs["glazingRatio"] = new_gr
    return make_layout_diff(
        room, "window", win.get("name", "window"),
        f"removed {win.get('name', 'window')}; glazing {old_gr:.2f}->{new_gr:.2f}",
        "visual+thermal",
        at=_anchor(win_geom), el=win_geom,
    )


def apply_remove_door(layout: dict, room: Optional[dict], hint: str = "") -> dict:
    """Remove a door, but REFUSE if it would leave a connected room with no door at all
    (sealing it off). Returns the diff, or {} if the guard blocks it."""
    if not room:
        return {}
    rid = room.get("id")
    doors = [d for d in layout.get("doors", [])
             if rid in d.get("attributes", {}).get("connectsRooms", [])]
    if not doors:
        doors = [d for d in layout.get("doors", []) if hint and hint.lower() in d.get("name", "").lower()]
    if not doors:
        return {}
    door = _match_named(doors, hint) or doors[0]
    conn = door.get("attributes", {}).get("connectsRooms", [])
    # connectivity guard: every connected room must keep at least one other door
    remaining = {}
    for d in layout.get("doors", []):
        if d is door:
            continue
        for r in d.get("attributes", {}).get("connectsRooms", []):
            remaining[r] = remaining.get(r, 0) + 1
    if any(remaining.get(r, 0) == 0 for r in conn):
        return {}   # would isolate a room — apply_edits records the rejection
    door_geom = door.get("geometry")
    layout["doors"] = [d for d in layout.get("doors", []) if d is not door]
    return make_layout_diff(
        room, "door", door.get("name", "door"),
        f"removed {door.get('name', 'door')}", "acoustic+olfactory",
        at=_anchor(door_geom), el=door_geom,
    )
