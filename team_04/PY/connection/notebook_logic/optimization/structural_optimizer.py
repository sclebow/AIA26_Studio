"""Structural feasibility scorer — slenderness, symmetry, lateral stability."""
from __future__ import annotations

from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    if len(b) < 3:
        return {"score": 50.0, "metrics": {}, "reason": "no footprint"}
    w, h, *_ = _geom.extent(b)
    base = max(1.0, min(w, h))
    floors = int(candidate.get("floors") or 1)
    height = floors * 3.0
    # Slenderness ratio (height / base width). >7 is challenging; <=4 is comfortable.
    slenderness = height / base
    slender_ok = _geom.clamp01(1.0 - max(0.0, slenderness - 4.0) / 6.0)
    # Symmetry: aspect ratio near 1 (and even vertex count) → more lateral stability.
    aspect = max(w, h) / base
    symmetry = _geom.clamp01(1.0 - (aspect - 1.0) / 3.0)
    s = 0.6 * slender_ok + 0.4 * symmetry
    return {
        "score": round(s * 100, 1),
        "metrics": {
            "structural_feasibility": round(s * 100),
            "slenderness_ratio": round(slenderness, 2),
            "lateral_stability": round(symmetry * 100),
        },
        "reason": f"slenderness {round(slenderness,1)}, stability {round(symmetry*100)}",
    }
