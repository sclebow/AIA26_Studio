"""
_edits.py — shared helpers for layout-editing tools.
Fixed: floor material support (reads/writes room.attributes.floorMaterial).
"""

from __future__ import annotations
import json
from typing import Any, Optional

MATERIALS = ["carpet", "fabric", "wood", "cork", "plaster", "brick",
             "ceramic", "stone", "concrete", "glass", "metal", "natural"]

SOFT_FURNITURE = {"sofa", "bed", "armchair", "rug", "cushion", "couch"}
FURNITURE_TYPES = list(SOFT_FURNITURE) + ["table", "desk", "shelf", "bookshelf",
                                           "cabinet", "dresser", "plant"]

FLOOR_KEYWORDS = ("floor", "flooring", "ground", "underfoot")
WALL_KEYWORDS  = ("wall", "walls", "partition", "ceiling")


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

    # 1. explicit room name or room type in the prompt
    for room in rooms:
        name  = (room.get("name") or "").lower()
        rtype = (room.get("attributes", {}).get("roomType") or "").lower()
        if (name and name in p) or (rtype and rtype in p):
            return room

    # 2. hint from action_classifier (LLM-extracted room name)
    if hint:
        h = hint.lower()
        for room in rooms:
            name  = (room.get("name") or "").lower()
            rtype = (room.get("attributes", {}).get("roomType") or "").lower()
            if (name and name in h) or (rtype and rtype in h):
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
    return "{}-{}".format(prefix, len(layout.get(key, [])) + 1)


def make_layout_diff(room: Optional[dict], attribute: str,
                     old_value: Any, new_value: Any,
                     sense_affected: str) -> dict:
    """Build the structured diff payload for the frontend."""
    if room is None:
        return {}
    return {
        "room_id":       room.get("id", ""),
        "room_name":     room.get("name", "unknown"),
        "attribute":     attribute,
        "old_value":     old_value,
        "new_value":     new_value,
        "sense_affected": sense_affected,
    }


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
        old_vals = [w.get("attributes", {}).get("material", "plaster")
                    for w in layout.get("structure", [])]
        old_val  = old_vals[0] if old_vals else "plaster"
        for w in layout.get("structure", []):
            w.setdefault("attributes", {})["material"] = material
        return make_layout_diff(room, "wallMaterial", old_val, material, "tactile")

    if room:
        rid     = room.get("id")
        changed = False
        old_val = material
        for f in layout.get("furniture", []):
            if f.get("attributes", {}).get("roomId") == rid:
                old_val = f.get("attributes", {}).get("material", "unknown")
                f.setdefault("attributes", {})["material"] = material
                changed = True
        return make_layout_diff(
            room, "furnitureMaterial", old_val if changed else "none", material, "tactile"
        )

    return {}


def apply_add_furniture(layout: dict, room: Optional[dict],
                        ftype: str, material: str) -> dict:
    """Append a furniture/plant element to `room` in `layout`. Returns the diff."""
    if not room:
        return {}
    cx, cy = centroid(room.get("geometry", []))
    h = 0.4
    geo = [[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h],
           [cx - h, cy + h], [cx - h, cy - h]]
    new_id = next_id(layout, "furniture", "furn")
    layout.setdefault("furniture", []).append({
        "id": new_id,
        "name": f"Added {ftype}",
        "geometry": geo,
        "attributes": {"roomId": room.get("id"), "type": ftype, "material": material},
    })
    sense = "olfactory+visual" if ftype == "plant" else "tactile"
    return make_layout_diff(room, "furniture", "none", f"added {ftype} ({material})", sense)


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
    rid    = room.get("id")
    old_gt = "double"
    for win in layout.get("windows", []):
        if win.get("attributes", {}).get("roomId") == rid:
            old_gt = win.get("attributes", {}).get("glazingType", "double")
            win.setdefault("attributes", {})["glazingType"] = applied_gt

    return make_layout_diff(
        room, "glazingRatio",
        f"ratio={old_gr:.2f}, type={old_gt}",
        f"ratio={new_gr:.2f}, type={applied_gt}",
        "visual+thermal",
    )
