"""Option diversity — drop near-duplicate optimization options so the best-N set is
genuinely different (position / rotation / footprint / shape / score), keeping the
higher-scoring option when two are almost identical.

The NSGA-II Pareto front often collapses to many tied-score solutions at nearly the
same place on an easy site; without this the "4 options" look identical.
"""
from __future__ import annotations

import copy
from typing import Any


def _centroid(boundary) -> tuple[float, float]:
    pts = [(float(p[0]), float(p[1])) for p in (boundary or []) if len(p) >= 2]
    if not pts:
        return 0.0, 0.0
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _similar(a: dict[str, Any], b: dict[str, Any], *, pos_tol: float, rot_tol: float, area_tol: float) -> bool:
    """Two options are 'the same' if same shape type AND close in position, rotation
    and footprint area."""
    if (a.get("shape_type") or "") != (b.get("shape_type") or ""):
        return False
    ax, ay = _centroid(a.get("boundary"))
    bx, by = _centroid(b.get("boundary"))
    if ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 > pos_tol:
        return False
    ra, rb = float(a.get("rotation_degrees", 0) or 0), float(b.get("rotation_degrees", 0) or 0)
    drot = abs((ra - rb) % 360)
    drot = min(drot, 360 - drot)
    if drot > rot_tol:
        return False
    aa, ba = float(a.get("footprint_area", 0) or 0), float(b.get("footprint_area", 0) or 0)
    if max(aa, ba) > 0 and abs(aa - ba) / max(aa, ba) > area_tol:
        return False
    return True


def dedupe(
    options: list[dict[str, Any]],
    *,
    top_n: int = 4,
    pos_tol: float = 8.0,       # meters — closer than this counts as the same spot
    rot_tol: float = 12.0,      # degrees
    area_tol: float = 0.08,     # 8% footprint-area difference
) -> list[dict[str, Any]]:
    """Return up to top_n DISTINCT options (deep-copied), best score first. Drops a
    candidate if it's near-identical to an already-kept (higher-scoring) one."""
    ranked = sorted(options, key=lambda o: float(o.get("score", o.get("combined_score", 0)) or 0), reverse=True)
    kept: list[dict[str, Any]] = []
    for cand in ranked:
        if any(_similar(cand, k, pos_tol=pos_tol, rot_tol=rot_tol, area_tol=area_tol) for k in kept):
            continue  # near-duplicate of a higher-scoring kept option → skip
        kept.append(copy.deepcopy(cand))  # deepcopy so options never share geometry
        if len(kept) >= top_n:
            break
    # Re-id / re-rank the surviving distinct options.
    for i, o in enumerate(kept):
        o["rank"] = i + 1
        o["option_id"] = o.get("option_id") or f"opt_{i + 1:02d}"
    return kept


def ensure_count(
    options: list[dict[str, Any]],
    pool: list[dict[str, Any]],
    *,
    top_n: int = 4,
) -> list[dict[str, Any]]:
    """If dedupe left fewer than top_n options, top up from the remaining pool with
    the next-best distinct-ish candidates (deep-copied) so the user still gets N."""
    if len(options) >= top_n:
        return options[:top_n]
    have_ids = {id(o) for o in options}
    extras = sorted(
        (o for o in pool if id(o) not in have_ids),
        key=lambda o: float(o.get("score", o.get("combined_score", 0)) or 0),
        reverse=True,
    )
    out = list(options)
    for e in extras:
        out.append(copy.deepcopy(e))
        if len(out) >= top_n:
            break
    for i, o in enumerate(out):
        o["rank"] = i + 1
        o["option_id"] = f"opt_{i + 1:02d}"
    return out
