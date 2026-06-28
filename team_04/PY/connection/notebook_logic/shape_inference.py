"""Shape inference — decide which building typology/typologies to generate from a
prompt. If the user names a shape (U/L/H/I/T/courtyard…), use it. If they DON'T
(e.g. "a 6 floor commercial building"), generate MULTIPLE candidate typologies so
the user gets options across forms without choosing a shape first.

Reuses agent.decision_engine._infer_requested_building_type for the single-shape
case so there is one inference implementation.
"""
from __future__ import annotations

import re
from typing import Any

from agent.decision_engine import _infer_requested_building_type  # noqa: PLC2701 (reuse)

# Default typology set to explore when the prompt doesn't specify a shape. Kept
# small so multi-shape generation stays fast; "O" (courtyard/ring) included for
# the courtyard typology the prompt mentions.
DEFAULT_TYPOLOGIES = ["I", "L", "U", "H", "T", "O"]

_FLOOR_HEIGHT_M = 3.0

_USE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("commercial", "commercial"), ("retail", "commercial"), ("office", "office"),
    ("residential", "residential"), ("apartment", "residential"), ("housing", "residential"),
    ("hotel", "hospitality"), ("mixed use", "mixed_use"), ("mixed-use", "mixed_use"),
    ("institutional", "institutional"),
)


def infer_floors(prompt: str) -> int | None:
    low = (prompt or "").lower()
    m = re.search(r"\bg\s*\+\s*(\d+)\b", low)
    if m:
        return int(m.group(1)) + 1
    m = re.search(r"(\d+)\s*(?:-|\s)?\s*(?:floors?|storey?s?|stories|levels?)\b", low)
    if m and int(m.group(1)) > 0:
        return int(m.group(1))
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    m = re.search(r"\b(" + "|".join(words) + r")\s*(?:-|\s)?\s*(?:floors?|storey?s?|stories|levels?)\b", low)
    return words[m.group(1)] if m else None


def infer_use(prompt: str) -> str | None:
    low = (prompt or "").lower()
    for kw, tag in _USE_KEYWORDS:
        if kw in low:
            return tag
    return None


def detect_shape_type(prompt: str) -> str | None:
    """Return the building-type letter the prompt names (U/L/H/I/T/X/Y/O), or None
    if no shape is specified. Public alias for the spec's detect_shape_type()."""
    return _infer_requested_building_type(prompt)


def infer_program(prompt: str) -> dict[str, Any]:
    """Full inference: shape (or 'auto' + typologies), floors→height, use."""
    shape = _infer_requested_building_type(prompt)
    floors = infer_floors(prompt)
    use = infer_use(prompt)
    height_m = round(floors * _FLOOR_HEIGHT_M, 2) if floors else None
    if shape:
        typologies = [shape]
        shape_type = shape
    else:
        # No shape named → explore multiple typologies.
        typologies = list(DEFAULT_TYPOLOGIES)
        shape_type = "auto"
    return {
        "shape_type": shape_type,        # a letter, or "auto"
        "typologies": typologies,        # the list to generate
        "is_multi": shape_type == "auto",
        "floors": floors,
        "floor_height_m": _FLOOR_HEIGHT_M,
        "height_m": height_m,
        "building_use": use,
    }
