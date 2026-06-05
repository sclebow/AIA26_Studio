"""
imaging/prompt.py — turn a room's comfort scores + persona into a text-to-image
prompt for a first-person "how it feels to be there" interior render.

Score → prompt mapping follows the deep-research findings (docs/week08/
image-generation-research.md): each 0-1 sense score drives concrete, visible scene
qualities (palette, lighting, surfaces, volume, air, materials). Only strong
signals (clearly low or clearly high) are voiced, so a room's *weak* senses set the
mood — that's the point: discomfort should be visible.
"""

from __future__ import annotations
from typing import Any

# sense → (low fragment <0.45, high fragment >0.70). Mid-range stays silent.
_SENSE_FRAGMENTS = {
    "thermal":   ("a cool, slightly cold feel with bluish daylight",
                  "a warm, cosy feel with golden light"),
    "visual":    ("dim, harsh and visually cluttered with uneven lighting",
                  "bright, airy and visually calm with balanced natural light"),
    "acoustic":  ("hard reflective surfaces — bare concrete, glass and tile — that look acoustically live",
                  "soft sound-absorbing textiles, rugs and drapes"),
    "spatial":   ("cramped and tight with a low ceiling",
                  "open, spacious and generous in volume"),
    "olfactory": ("stuffy and closed with stale air",
                  "fresh and well-ventilated, with a few plants"),
    "tactile":   ("cold, hard, unwelcoming materials",
                  "warm natural materials like wood and wool"),
}

_REGISTER = {
    "architect": "Shot as restrained, material-honest architectural photography.",
    "client":    "Shot as warm, inviting lifestyle interior photography.",
    "student":   "Shot as a cosy, practical real-world interior photo.",
}


def build_room_prompt(room: dict[str, Any], scores: dict[str, float], persona: dict[str, Any] | None) -> str:
    """Compose the first-person interior render prompt for one room."""
    attrs = room.get("attributes", {}) or {}
    rtype = (attrs.get("roomType") or room.get("name") or "room").lower()
    material = attrs.get("floorMaterial")

    parts = [f"First-person, eye-level interior photograph of a {rtype}."]
    if material:
        parts.append(f"The floor is {material}.")

    frags = []
    for sense, (low, high) in _SENSE_FRAGMENTS.items():
        v = scores.get(sense)
        if v is None:
            continue
        if v < 0.45:
            frags.append(low)
        elif v > 0.70:
            frags.append(high)
    if frags:
        parts.append("The space feels " + "; ".join(frags) + ".")

    parts.append("Natural perspective, 35mm lens, photorealistic, high detail, no text, no people.")
    role = (persona or {}).get("role", "")
    parts.append(_REGISTER.get(role, "Realistic interior photography."))
    return " ".join(parts)
