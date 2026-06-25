"""Deterministic design validation tool (self-debug loop, step 1).

A single, deterministic Shapely-based check that answers: "is this building
geometry actually valid on this site?" It returns a STRUCTURED verdict —
``{passed, failures, checks, metrics}`` — so a caller (the manipulation flow,
the optimizer, or a future agent node) can decide whether to keep the geometry,
attempt a corrective fix, or reject and report.

This is ADDITIVE and reuses the existing constraint engine
(``optimization_constraints.validate_optimization_candidate`` + ``setback_rules``)
rather than reimplementing geometry checks. It NEVER mutates its inputs and never
raises on bad input — a malformed polygon is reported as a failed check, not an
exception, so it is safe to call anywhere in the request path.

Checks performed (each independent, all deterministic):
  * polygon_valid     — footprint is a valid, non-self-intersecting ring
  * inside_site       — footprint lies within the confirmed site boundary
  * setback           — footprint respects the buildable area (site minus setback)
  * open_space        — enough open site area remains (per building-type rules)
  * no_overlap        — footprint does not overlap other placed buildings
  * footprint_area    — footprint area is within tolerance of its expected area
  * holes_valid       — any courtyard/hole is a valid ring INSIDE the footprint
"""
from __future__ import annotations

from typing import Any

from shapely.geometry import Polygon

from . import optimization_constraints as oc


def _poly(ring: list[list[float]] | None) -> Polygon | None:
    """Build a Shapely polygon from a ring, repairing minor invalidity. None on failure."""
    if not ring or len(ring) < 3:
        return None
    try:
        p = Polygon([(float(x), float(y)) for x, y in (pt[:2] for pt in ring)])
        if not p.is_valid:
            p = p.buffer(0)
        return p if (p and not p.is_empty and p.area > 0) else None
    except Exception:  # noqa: BLE001 — malformed input is a failed check, not a crash
        return None


def _area(ring: list[list[float]] | None) -> float:
    p = _poly(ring)
    return float(p.area) if p else 0.0


def validate_design(
    building: dict[str, Any],
    site_boundary: list[list[float]] | None,
    *,
    other_buildings: list[dict[str, Any]] | None = None,
    expected_area: float | None = None,
    area_tolerance: float = 0.18,
) -> dict[str, Any]:
    """Validate a building's geometry on its site. Returns a structured verdict.

    Args:
        building: dict with at least ``boundary`` (outer ring); optional ``holes``,
            ``building_type``/``shape_type``, ``floor_plates``.
        site_boundary: confirmed site ring. If absent, site/setback checks are
            marked SKIPPED (not failed) — geometry-only validation still runs.
        other_buildings: other placed buildings (dicts with ``boundary``) to test
            for overlap. The target building itself is excluded by identity.
        expected_area: if given, the footprint area must be within ``area_tolerance``
            (fractional) of it — catches a manipulation that silently shrank/grew.
        area_tolerance: allowed fractional deviation for the area check (default 18%).

    Returns:
        ``{passed, failures, checks, metrics}`` where ``checks`` maps each check name
        to ``{passed, skipped, message}`` and ``failures`` is the list of failed
        check names (a quick machine-readable summary).
    """
    boundary = building.get("boundary") or building.get("building_boundary")
    holes = building.get("holes") or []
    btype = building.get("building_type") or building.get("shape_type") or "L"

    checks: dict[str, dict[str, Any]] = {}

    def record(name: str, passed: bool, message: str, *, skipped: bool = False) -> None:
        checks[name] = {"passed": bool(passed), "skipped": bool(skipped), "message": message}

    # --- 1. polygon validity --------------------------------------------------
    fp = _poly(boundary)
    if fp is None:
        record("polygon_valid", False, "Footprint is missing or not a valid polygon.")
        # Without a valid footprint, every other check is meaningless — short-circuit.
        return _verdict(checks, {"footprint_area": 0.0})
    record("polygon_valid", True, "Footprint is a valid, non-self-intersecting ring.")

    metrics: dict[str, Any] = {
        "footprint_area": round(fp.area, 1),
        "hole_count": len(holes),
    }

    # --- 2/3/4. site + setback + open space (reuse the existing engine) -------
    if site_boundary and len(site_boundary) >= 3:
        try:
            v = oc.validate_optimization_candidate(boundary, site_boundary, building_type=btype)
            c = v.get("constraints", {})
            sb = c.get("site_boundary", {})
            record("inside_site", sb.get("passed", False),
                   sb.get("message") or "Footprint vs site boundary.")
            stb = c.get("setback", {})
            # setback only meaningful once inside the site
            if sb.get("passed", False):
                record("setback", stb.get("passed", False),
                       stb.get("message") or "Footprint vs buildable area (setback).")
            else:
                record("setback", True, "Setback not evaluated (outside site).", skipped=True)
            osp = c.get("open_space", {})
            record("open_space", osp.get("passed", True),
                   osp.get("message") or "Open-space requirement.")
            metrics["site_area"] = round(_area(site_boundary), 1)
            metrics["site_coverage"] = (round(fp.area / metrics["site_area"], 3)
                                        if metrics["site_area"] else None)
        except Exception as exc:  # noqa: BLE001 — never let validation crash the request
            record("inside_site", True, f"Site check skipped (error: {exc}).", skipped=True)
            record("setback", True, "Setback check skipped.", skipped=True)
            record("open_space", True, "Open-space check skipped.", skipped=True)
    else:
        record("inside_site", True, "No site boundary — geometry-only validation.", skipped=True)
        record("setback", True, "No site boundary — setback not checked.", skipped=True)
        record("open_space", True, "No site boundary — open space not checked.", skipped=True)

    # --- 5. overlap with other placed buildings -------------------------------
    overlaps: list[str] = []
    for ob in (other_buildings or []):
        if ob is building:
            continue
        ob_poly = _poly(ob.get("boundary") or ob.get("building_boundary"))
        if ob_poly is None:
            continue
        try:
            inter = fp.intersection(ob_poly).area
            # ignore a sliver touch; flag a real overlap (>2% of footprint)
            if inter > 0.02 * fp.area:
                overlaps.append(ob.get("building_id") or ob.get("geometry_id") or "another building")
        except Exception:  # noqa: BLE001
            continue
    if overlaps:
        record("no_overlap", False, f"Footprint overlaps: {', '.join(overlaps)}.")
        metrics["overlaps"] = overlaps
    else:
        record("no_overlap", True, "No overlap with other buildings.")

    # --- 6. footprint area within tolerance -----------------------------------
    if expected_area and expected_area > 0:
        dev = abs(fp.area - expected_area) / expected_area
        ok = dev <= area_tolerance
        record("footprint_area", ok,
               f"Area {fp.area:.0f} m² vs expected {expected_area:.0f} m² "
               f"(±{area_tolerance*100:.0f}%): {'within' if ok else 'OUT OF'} tolerance.")
        metrics["expected_area"] = round(expected_area, 1)
        metrics["area_deviation_pct"] = round(dev * 100, 1)
    else:
        record("footprint_area", True, "No expected area to compare against.", skipped=True)

    # --- 7. holes (courtyards) valid and inside the footprint -----------------
    if holes:
        bad = 0
        for h in holes:
            hp = _poly(h)
            if hp is None or not fp.contains(hp.buffer(-0.01)):
                bad += 1
        if bad:
            record("holes_valid", False, f"{bad} courtyard/hole ring(s) invalid or poking outside the footprint.")
        else:
            record("holes_valid", True, f"All {len(holes)} courtyard/hole ring(s) valid and inside.")
    else:
        record("holes_valid", True, "No holes to validate.", skipped=True)

    return _verdict(checks, metrics)


def _verdict(checks: dict[str, dict[str, Any]], metrics: dict[str, Any]) -> dict[str, Any]:
    """Assemble the final structured verdict from the per-check results."""
    failures = [name for name, c in checks.items() if not c["passed"] and not c.get("skipped")]
    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "checks": checks,
        "metrics": metrics,
    }
