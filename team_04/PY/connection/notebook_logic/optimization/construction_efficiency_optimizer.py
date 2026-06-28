"""Construction efficiency scorer — surface-to-volume, facade area, massing simplicity."""
from __future__ import annotations

from typing import Any

from . import _geom


def score(candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    b = candidate.get("boundary") or []
    if len(b) < 3:
        return {"score": 50.0, "metrics": {}, "reason": "no footprint"}
    area = _geom.area(b)
    perim = _geom.perimeter(b)
    floors = int(candidate.get("floors") or 1)
    fh = 3.0
    height = floors * fh
    # Surface-to-volume ratio (lower = more efficient envelope). Facade + roof vs volume.
    facade = perim * height
    roof = area
    volume = area * height
    s2v = (facade + roof) / max(1.0, volume)
    # Compactness: a circle has min perimeter for area; closer to that = simpler.
    import math
    compactness = (4 * math.pi * area) / max(1.0, perim * perim)  # 1.0 = circle
    # Fewer footprint vertices = simpler structural grid.
    simplicity = _geom.clamp01(1.0 - (len(b) - 4) / 16.0)
    eff = _geom.clamp01(0.4 * compactness + 0.35 * (1.0 - min(1.0, s2v / 0.6)) + 0.25 * simplicity)
    return {
        "score": round(eff * 100, 1),
        "metrics": {
            "surface_to_volume_ratio": round(s2v, 3),
            "structural_efficiency": round(simplicity * 100),
            "cost_efficiency": round(eff * 100),
            "compactness": round(compactness * 100),
        },
        "reason": f"compactness {round(compactness*100)}, S/V {round(s2v,2)}",
    }
