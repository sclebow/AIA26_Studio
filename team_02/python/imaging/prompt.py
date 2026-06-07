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

# Directional mood words for the explicit change clause. (down <- , up ->):
# index 0 reads when a sense went DOWN vs the reference, index 1 when it went UP.
_SENSE_DIRECTION = {
    "thermal":   ("cooler, with bluer daylight",        "warmer, with golden light"),
    "visual":    ("dimmer and more cluttered",          "brighter, airier and calmer"),
    "acoustic":  ("more echoey, with harder surfaces",  "softer and more sound-absorbing"),
    "spatial":   ("tighter and more enclosed",          "more open and spacious"),
    "olfactory": ("stuffier, with staler air",          "fresher and better-ventilated"),
    "tactile":   ("harder and colder underfoot",        "warmer, more natural materials"),
}


_COUNT_WORDS = {1: "a", 2: "two", 3: "three", 4: "four"}


def _count_word(n: int) -> str:
    return _COUNT_WORDS.get(n, "several")


def _furn_attr(f: dict[str, Any], key: str) -> str:
    """Furniture stores type/material under `attributes` (top-level is a fallback)."""
    a = f.get("attributes") or {}
    return str(a.get(key) or f.get(key) or "").strip().lower()


def _is_plant(f: dict[str, Any]) -> bool:
    return _furn_attr(f, "type") == "plant" or _furn_attr(f, "material") == "natural"


def _plant_count(furn: list[dict[str, Any]] | None) -> int:
    return sum(1 for f in (furn or []) if _is_plant(f))


def _type_materials(furn: list[dict[str, Any]] | None) -> dict[str, str]:
    """type → material for non-plant furniture (first seen wins)."""
    m: dict[str, str] = {}
    for f in furn or []:
        if _is_plant(f):
            continue
        typ = _furn_attr(f, "type")
        if typ and typ not in m:
            m[typ] = _furn_attr(f, "material")
    return m


def _article(word: str) -> str:
    return "an" if word[:1] in "aeiou" else "a"


def _furniture_phrase(furn: list[dict[str, Any]] | None) -> str:
    """A compact natural-language list of notable furnishings + their materials, so
    the render actually depicts the island material, plants, etc. — not just the floor."""
    if not furn:
        return ""
    phrases = []
    for typ, mat in list(_type_materials(furn).items())[:5]:
        label = f"{mat} {typ}".strip()
        phrases.append(f"{_article(label)} {label}")
    plants = _plant_count(furn)
    if plants:
        phrases.append(f"{_count_word(plants)} potted plant" + ("s" if plants != 1 else ""))
    return "Furnishings include " + ", ".join(phrases) + "." if phrases else ""


def build_change_clause(
    room_target: dict[str, Any], room_ref: dict[str, Any],
    target_scores: dict[str, float], ref_scores: dict[str, float],
    furn_target: list[dict[str, Any]] | None = None,
    furn_ref: list[dict[str, Any]] | None = None,
    *, sense_eps: float = 0.04,
) -> str:
    """An IMPERATIVE edit instruction that transforms the reference image into the
    `room_target` state. Used for the anchored variant render: image-to-image copies
    the reference, so descriptive text is ignored — explicit edits ("change the floor
    to X; remove the plants") are what make every change visibly apparent. Symmetric:
    swap the args to describe the opposite direction.
    """
    at = room_target.get("attributes", {}) or {}
    ar = room_ref.get("attributes", {}) or {}
    edits: list[str] = []

    # envelope / material edits
    if at.get("floorMaterial") and at.get("floorMaterial") != ar.get("floorMaterial"):
        edits.append(f"change the floor to {at['floorMaterial']}")
    if at.get("glazingType") and at.get("glazingType") != ar.get("glazingType"):
        edits.append(f"fit {at['glazingType']} glazing")
    try:
        gr_t, gr_r = float(at.get("glazingRatio")), float(ar.get("glazingRatio"))
        if abs(gr_t - gr_r) >= 0.03:
            edits.append("enlarge the windows for more daylight" if gr_t > gr_r
                         else "shrink the windows for less daylight")
    except (TypeError, ValueError):
        pass

    # furniture: plants, per-type material swaps, and added/removed pieces
    pt, pr = _plant_count(furn_target), _plant_count(furn_ref)
    if pt > pr:
        edits.append(f"add {_count_word(pt - pr)} potted plant" + ("s" if pt - pr != 1 else ""))
    elif pr > pt:
        edits.append("remove the potted plants and any flowers")
    tmap, rmap = _type_materials(furn_target), _type_materials(furn_ref)
    for typ, mat in tmap.items():
        if typ in rmap and mat and rmap[typ] != mat:
            edits.append(f"make the {typ} {mat}")
    for typ in rmap.keys() - tmap.keys():       # present in ref, not target → remove it
        edits.append(f"remove the {typ}")
    for typ in tmap.keys() - rmap.keys():        # present in target, not ref → add it
        label = f"{tmap[typ]} {typ}".strip()
        edits.append(f"add {_article(label)} {label}")

    # mood edits — only senses that actually moved
    for sense, (down, up) in _SENSE_DIRECTION.items():
        vt, vr = target_scores.get(sense), ref_scores.get(sense)
        if vt is None or vr is None:
            continue
        if vt - vr >= sense_eps:
            edits.append(f"make it {up}")
        elif vr - vt >= sense_eps:
            edits.append(f"make it {down}")

    if not edits:
        return ""
    return ("Keep the same room, camera angle and viewpoint as the reference image, "
            "but edit it to show this state: " + "; ".join(edits[:9]) + ".")


def build_room_prompt(room: dict[str, Any], scores: dict[str, float],
                      persona: dict[str, Any] | None,
                      furniture: list[dict[str, Any]] | None = None) -> str:
    """Compose the first-person interior render prompt for one room. Includes notable
    furnishings + materials so changes to the island, plants, etc. are depicted."""
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

    fp = _furniture_phrase(furniture)
    if fp:
        parts.append(fp)

    parts.append("Natural perspective, 35mm lens, photorealistic, high detail, no text, no people.")
    role = (persona or {}).get("role", "")
    parts.append(_REGISTER.get(role, "Realistic interior photography."))
    return " ".join(parts)
