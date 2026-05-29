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
