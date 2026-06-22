"""Deterministic self-validation for a generated building footprint.

This is the hard, reproducible half of the agent's verify→debug→retry loop.
It answers one question — *did the last attempt actually work?* — with a
structured verdict the ``debug`` node can reason over:

    {
      "passed": bool,                 # all HARD checks ok (+ area within tolerance)
      "failures": ["outside_site", ...],   # debug vocabulary, drives the next fix
      "checks": [ {name, passed, detail, ...}, ... ],
      "metrics": {building_area_sqm, target_area_sqm, area_error_ratio, ...}
    }

The failure tokens (``invalid_polygon``, ``outside_site``, ``overlap``,
``area``) are the same vocabulary the debug node maps back to a corrective
action, so keep them stable. Every check is wrapped defensively: a malformed
boundary yields a failed check, never an exception that would crash the graph.
"""
from __future__ import annotations

from typing import Any

from shapely.geometry import Polygon
from shapely.validation import explain_validity

from .multi_building_mock import _normalize_polygon


VALIDATE_DESIGN_TOOL_DEFINITION: dict[str, Any] = {
    "name": "validate_design",
    "description": (
        "Validate a generated building footprint against hard design rules: the "
        "polygon must be geometrically valid, fit inside the site boundary, not "
        "overlap already-placed buildings, and (when a target is known) land "
        "within tolerance of the requested footprint area. Returns a structured "
        "pass/fail verdict with the failing checks so the agent can self-correct."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "geometry_id": {"type": "string"},
            "building_boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}},
                "description": "Closed building footprint as [x, y(, z)] coordinates.",
            },
            "site_boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}},
                "description": "Closed site boundary as [x, y(, z)] coordinates.",
            },
            "placed_buildings": {
                "type": "array",
                "description": "Already-placed building snapshots (each with a 'boundary').",
            },
            "target_area_sqm": {
                "type": "number",
                "description": "Requested footprint area; omit when the brief did not specify one.",
            },
            "area_tolerance": {
                "type": "number",
                "description": "Allowed fractional area error (0.25 = ±25%).",
                "default": 0.25,
            },
        },
        "required": ["building_boundary", "site_boundary"],
    },
}


def _polygon_from(points: Any) -> Polygon | None:
    """Build a shapely Polygon from a boundary, or None when it is unusable."""
    try:
        normalized = _normalize_polygon(points)
    except Exception:
        return None
    coords = [(float(p[0]), float(p[1])) for p in normalized]
    if len(coords) < 4:  # _normalize_polygon closes the ring, so <4 means <3 distinct pts
        return None
    try:
        polygon = Polygon(coords)
    except Exception:
        return None
    if polygon.is_empty:
        return None
    return polygon


def _placed_boundaries(placed_buildings: Any) -> list[list[list[float]]]:
    boundaries: list[list[list[float]]] = []
    if not isinstance(placed_buildings, list):
        return boundaries
    for item in placed_buildings:
        if isinstance(item, dict):
            boundary = item.get("boundary") or item.get("building_boundary")
            if isinstance(boundary, list) and len(boundary) >= 3:
                boundaries.append(boundary)
    return boundaries


def validate_design(
    building_boundary: list[list[float]],
    site_boundary: list[list[float]],
    placed_buildings: list[dict[str, Any]] | None = None,
    target_area_sqm: float | None = None,
    area_tolerance: float = 0.25,
    geometry_id: str = "",
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    metrics: dict[str, Any] = {}

    building = _polygon_from(building_boundary)
    site = _polygon_from(site_boundary)

    # ── 1. Valid polygon ────────────────────────────────────────────────────
    if building is None:
        checks.append({"name": "valid_polygon", "passed": False, "detail": "Boundary is not a usable closed polygon."})
        failures.append("invalid_polygon")
    elif not building.is_valid:
        checks.append({"name": "valid_polygon", "passed": False, "detail": explain_validity(building)})
        failures.append("invalid_polygon")
        # Self-intersection makes downstream area/fit meaningless; repair it first.
        building = building.buffer(0) if not building.is_empty else building
    else:
        checks.append({"name": "valid_polygon", "passed": True, "detail": "Closed, non-self-intersecting footprint."})

    building_area = float(building.area) if building is not None and not building.is_empty else 0.0
    metrics["building_area_sqm"] = round(building_area, 3)

    # ── 2. Fits inside the site ─────────────────────────────────────────────
    if building is None or site is None or building.is_empty or site.is_empty:
        checks.append({"name": "fits_site", "passed": False, "detail": "Missing usable building or site polygon."})
        if "invalid_polygon" not in failures:
            failures.append("outside_site")
    else:
        outside_area = float(building.difference(site).area)
        outside_ratio = (outside_area / building_area) if building_area > 0 else 1.0
        metrics["area_outside_site_sqm"] = round(outside_area, 3)
        metrics["fraction_outside_site"] = round(outside_ratio, 4)
        # Tiny spill (< 0.5% or 0.5 m²) is numerical noise, not a real violation.
        fits = outside_area <= max(0.5, building_area * 0.005)
        checks.append({
            "name": "fits_site",
            "passed": fits,
            "detail": f"{outside_ratio * 100:.1f}% of the footprint falls outside the site.",
        })
        if not fits:
            failures.append("outside_site")

    # ── 3. No overlap with already-placed buildings ─────────────────────────
    placed = _placed_boundaries(placed_buildings)
    if building is None or building.is_empty or not placed:
        checks.append({"name": "no_overlap", "passed": True, "detail": f"{len(placed)} placed building(s); no overlap." if placed else "No placed buildings to overlap."})
    else:
        worst_overlap = 0.0
        for other in placed:
            other_polygon = _polygon_from(other)
            if other_polygon is None or other_polygon.is_empty:
                continue
            overlap = float(building.intersection(other_polygon).area)
            worst_overlap = max(worst_overlap, overlap)
        overlap_ratio = (worst_overlap / building_area) if building_area > 0 else 0.0
        metrics["worst_overlap_sqm"] = round(worst_overlap, 3)
        metrics["worst_overlap_ratio"] = round(overlap_ratio, 4)
        clear = worst_overlap <= max(0.5, building_area * 0.005)
        checks.append({
            "name": "no_overlap",
            "passed": clear,
            "detail": f"Largest overlap with a placed building is {overlap_ratio * 100:.1f}% of the footprint.",
        })
        if not clear:
            failures.append("overlap")

    # ── 4. Footprint area within tolerance (soft, only when a target exists) ─
    if isinstance(target_area_sqm, (int, float)) and float(target_area_sqm) > 0 and building_area > 0:
        target = float(target_area_sqm)
        tolerance = float(area_tolerance) if area_tolerance and area_tolerance > 0 else 0.25
        area_error = abs(building_area - target) / target
        metrics["target_area_sqm"] = round(target, 3)
        metrics["area_error_ratio"] = round(area_error, 4)
        area_ok = area_error <= tolerance
        checks.append({
            "name": "area_within_tolerance",
            "passed": area_ok,
            "detail": f"Footprint {building_area:.0f} m² vs target {target:.0f} m² ({area_error * 100:.0f}% error, tol {tolerance * 100:.0f}%).",
        })
        if not area_ok:
            failures.append("area")

    # de-duplicate while preserving order
    ordered_failures = list(dict.fromkeys(failures))
    passed = not ordered_failures

    data: dict[str, Any] = {
        "passed": passed,
        "failures": ordered_failures,
        "checks": checks,
        "metrics": metrics,
        "summary": (
            "All design checks passed."
            if passed
            else "Failed checks: " + ", ".join(ordered_failures) + "."
        ),
    }
    if geometry_id:
        data["geometry_id"] = geometry_id

    return {
        "success": True,
        "data": data,
        "metadata": {
            "tool_name": VALIDATE_DESIGN_TOOL_DEFINITION["name"],
            "source": "python",
        },
    }
