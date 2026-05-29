"""
_edits.py — shared helpers for the real layout-editing tools (Phase 5).

The MOD tools (change_material / modify_glazing / add_furniture) now mutate the
layout JSON for real, so the downstream analyze → compare_versions loop produces
genuine before/after deltas instead of zeros.

Target-room and value extraction from the user's free-text prompt is heuristic
(keyword matching + worst-room fallback). A future improvement is an LLM-based
argument extractor; flagged for review.
"""

from __future__ import annotations
import json
from typing import Any, Optional

# Tactile-warmth materials known to compute_comfort_scores.
MATERIALS = ["carpet", "fabric", "wood", "cork", "plaster", "brick",
             "ceramic", "stone", "concrete", "glass", "metal", "natural"]

# Furniture types the scorer reacts to (soft → tactile/acoustic, plant → olfactory/visual).
SOFT_FURNITURE = {"sofa", "bed", "armchair", "rug", "cushion", "couch"}
FURNITURE_TYPES = list(SOFT_FURNITURE) + ["table", "desk", "shelf", "bookshelf",
                                          "cabinet", "dresser", "plant"]


def load(layout_json_string: str) -> Optional[dict]:
    try:
        return json.loads(layout_json_string)
    except Exception:
        return None


def dump(layout: dict) -> str:
    return json.dumps(layout)


def worst_room_name(scores_json: str) -> Optional[str]:
    """Name of the lowest-scoring room from a compute_comfort_scores payload."""
    try:
        rooms = json.loads(scores_json).get("rooms", [])
        if not rooms:
            return None
        return min(rooms, key=lambda r: r.get("overallScore", 1.0)).get("roomName")
    except Exception:
        return None


def find_target_room(layout: dict, prompt: str, scores_json: str = "") -> Optional[dict]:
    """Pick the room the edit applies to: named in the prompt, else worst-scoring, else first."""
    rooms = layout.get("rooms", [])
    if not rooms:
        return None
    p = (prompt or "").lower()

    # 1. explicit room name or room type in the prompt
    for room in rooms:
        name = (room.get("name") or "").lower()
        rtype = (room.get("attributes", {}).get("roomType") or "").lower()
        if (name and name in p) or (rtype and rtype in p):
            return room

    # 2. worst-scoring room (so "fix the worst room" style requests land sensibly)
    worst = worst_room_name(scores_json)
    if worst:
        for room in rooms:
            if (room.get("name") or "") == worst:
                return room

    # 3. fallback: first room
    return rooms[0]


def detect_material(prompt: str) -> Optional[str]:
    p = (prompt or "").lower()
    for m in MATERIALS:
        if m in p:
            return m
    if "soft" in p or "warm" in p or "cosy" in p or "cozy" in p:
        return "fabric"
    return None


def detect_furniture_type(prompt: str) -> str:
    p = (prompt or "").lower()
    for t in FURNITURE_TYPES:
        if t in p:
            return t
    if "green" in p or "biophilic" in p:
        return "plant"
    return "plant"  # default: a plant (a common comfort recommendation)


def centroid(geometry: list) -> tuple[float, float]:
    pts = geometry or []
    if pts and len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def next_id(layout: dict, key: str, prefix: str) -> str:
    return "{}-{}".format(prefix, len(layout.get(key, [])) + 1)
