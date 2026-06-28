"""Self-debug helper (self-debug loop, step 2).

Given a building whose geometry FAILED ``validate_design``, propose a DETERMINISTIC
corrective transform and return the fixed footprint. This is the "debug" half of the
validate → debug → retry loop: it never invents geometry from scratch, it only nudges
the EXISTING footprint back into compliance (move inside the site, shrink to the
buildable area, separate from an overlapping neighbour).

Pure functions, no LLM required — like the rest of the runtime, the deterministic path
is load-bearing and always available. ``run_self_debug`` ties it to ``validate_design``
and re-validates after each attempt, bounded by ``max_attempts`` so a hopeless case
still terminates and is reported rather than looping forever.
"""
from __future__ import annotations

from typing import Any, Callable

from shapely.affinity import scale as _scale, translate as _translate
from shapely.geometry import Polygon

from . import setback_rules as sr
from . import validate_design as vd


def _poly(ring: list[list[float]] | None) -> Polygon | None:
    return vd._poly(ring)  # reuse the same tolerant builder


def _ring(poly: Polygon) -> list[list[float]]:
    return [[round(x, 3), round(y, 3)] for x, y in poly.exterior.coords]


def propose_fix(
    building: dict[str, Any],
    failures: list[str],
    site_boundary: list[list[float]] | None,
) -> dict[str, Any] | None:
    """Propose ONE corrective transform for the worst current failure.

    Returns ``{"boundary": <new ring>, "op": <what was done>}`` or None if no
    deterministic fix applies to these failures. Holes are carried by the SAME
    transform so a courtyard stays registered to its footprint.
    """
    fp = _poly(building.get("boundary") or building.get("building_boundary"))
    if fp is None:
        return None
    btype = building.get("building_type") or building.get("shape_type") or "L"
    site = _poly(site_boundary) if site_boundary and len(site_boundary) >= 3 else None

    # The buildable area = site minus setback. Fixes target THIS, so a corrected
    # footprint also clears the setback, not just the raw site edge.
    buildable = None
    if site is not None:
        try:
            ba = sr.create_buildable_area(site_boundary, building_type=btype)
            buildable = _poly(ba) if ba else site
        except Exception:  # noqa: BLE001
            buildable = site

    transform: Callable[[Polygon], Polygon] | None = None
    op = None

    # Priority 1: outside the site / setback → translate the centroid toward the
    # buildable centroid, then (if still outside) shrink to fit inside it.
    if buildable is not None and ("inside_site" in failures or "setback_violation" in failures
                                  or "setback" in failures):
        bcx, bcy = fp.centroid.x, fp.centroid.y
        tcx, tcy = buildable.centroid.x, buildable.centroid.y
        dx, dy = tcx - bcx, tcy - bcy
        moved = _translate(fp, dx, dy)
        if buildable.contains(moved):
            transform = lambda g: _translate(g, dx, dy)
            op = "moved inside buildable area"
        else:
            # shrink toward the buildable centroid until it fits (a few steps).
            factor = 1.0
            fitted = None
            for _ in range(6):
                factor *= 0.92
                cand = _scale(moved, xfact=factor, yfact=factor, origin=(tcx, tcy))
                if buildable.contains(cand):
                    fitted = (dx, dy, factor)
                    break
            if fitted:
                _dx, _dy, _f = fitted
                transform = lambda g: _scale(_translate(g, _dx, _dy), xfact=_f, yfact=_f, origin=(tcx, tcy))
                op = f"moved + shrank ×{round(_f, 2)} to fit setback"

    # Priority 2: overlapping another building → nudge away along the centroid
    # vector from the overlap (small, bounded push; re-validated by the caller).
    elif "no_overlap" in failures:
        # push the footprint a fixed fraction of its size away from the site centre
        # (a cheap, deterministic separation that the loop re-checks).
        push = (fp.bounds[2] - fp.bounds[0]) * 0.25 or 4.0
        ref = (site.centroid if site is not None else fp.centroid)
        vx, vy = fp.centroid.x - ref.x, fp.centroid.y - ref.y
        norm = (vx * vx + vy * vy) ** 0.5 or 1.0
        dx, dy = (vx / norm) * push, (vy / norm) * push
        transform = lambda g: _translate(g, dx, dy)
        op = "nudged to separate from overlap"

    # Priority 3: footprint area out of tolerance → scale toward expected area
    # about the centroid (only when we can't do better above).
    elif "footprint_area" in failures:
        # caller passes expected via building; we only have current — gentle 0.95/1.05
        # correction toward typical isn't reliable without the target, so skip unless
        # the building carries an expected_area hint.
        exp = building.get("_expected_area")
        if exp and fp.area > 0:
            f = (exp / fp.area) ** 0.5
            f = max(0.6, min(1.6, f))  # bound the correction
            transform = lambda g: _scale(g, xfact=f, yfact=f, origin="centroid")
            op = f"rescaled ×{round(f, 2)} toward expected area"

    if transform is None or op is None:
        return None

    new_fp = transform(fp)
    if new_fp is None or new_fp.is_empty or new_fp.area <= 0:
        return None
    return {"boundary": _ring(new_fp), "op": op, "_transform": transform}


def run_self_debug(
    building: dict[str, Any],
    site_boundary: list[list[float]] | None,
    *,
    other_buildings: list[dict[str, Any]] | None = None,
    expected_area: float | None = None,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Validate → fix → re-validate, up to ``max_attempts``.

    Returns ``{ok, building, verdict, attempts, log}``:
      * ``ok``       — True if a valid geometry was reached (no fix needed, or fixed)
      * ``building`` — the (possibly corrected) building dict; holes carried with it
      * ``verdict``  — the final ``validate_design`` result
      * ``attempts`` — number of corrective passes actually applied
      * ``log``      — human-readable trail of what was tried

    The ORIGINAL building dict is never mutated — a shallow copy is returned when a
    fix is applied, so the caller can choose to keep or discard it.
    """
    log: list[str] = []
    work = building
    verdict = vd.validate_design(work, site_boundary, other_buildings=other_buildings,
                                 expected_area=expected_area)
    if verdict["passed"]:
        return {"ok": True, "building": work, "verdict": verdict, "attempts": 0,
                "log": ["valid on first check — no debug needed"]}

    attempts = 0
    for _ in range(max(0, max_attempts)):
        fix = propose_fix(work, verdict["failures"], site_boundary)
        if not fix:
            log.append(f"no deterministic fix for {verdict['failures']}")
            break
        attempts += 1
        # apply the fix to a COPY (carry holes through the same transform)
        nxt = dict(work)
        nxt["boundary"] = fix["boundary"]
        tr = fix.get("_transform")
        if tr and work.get("holes"):
            new_holes = []
            for h in work["holes"]:
                hp = _poly(h)
                new_holes.append(_ring(tr(hp)) if hp is not None else h)
            nxt["holes"] = new_holes
        log.append(f"attempt {attempts}: {fix['op']}")
        verdict = vd.validate_design(nxt, site_boundary, other_buildings=other_buildings,
                                     expected_area=expected_area)
        work = nxt
        if verdict["passed"]:
            log.append("✓ valid after fix")
            return {"ok": True, "building": work, "verdict": verdict, "attempts": attempts, "log": log}

    log.append(f"still invalid after {attempts} attempt(s): {verdict['failures']}")
    return {"ok": False, "building": work, "verdict": verdict, "attempts": attempts, "log": log}
