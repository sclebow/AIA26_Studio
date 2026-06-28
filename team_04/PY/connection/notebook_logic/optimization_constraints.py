"""Optimization constraints and validation.

Integrates setback, sunlight, edge-based, and boundary constraints.
Provides comprehensive validation and scoring for optimization candidates.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import Polygon

from . import edge_based_optimizer as ebo
from . import setback_rules as sr
from . import sunlight_analysis as sa


# ============================================================================
# Validation
# ============================================================================

def validate_optimization_candidate(
    candidate_boundary: list[list[float]],
    site_boundary: list[list[float]],
    building_type: str | None = None,
    setback_rules_override: sr.SetbackRules | None = None,
) -> dict[str, Any]:
    """Comprehensive validation of an optimization candidate.

    Args:
        candidate_boundary: Candidate building footprint
        site_boundary: Confirmed site boundary
        building_type: Building type for setback rules
        setback_rules_override: Custom setback rules (if None, uses building_type)

    Returns:
        Validation result dict
    """
    result = {
        "valid": False,
        "candidate_boundary": candidate_boundary,
        "constraints": {
            "site_boundary": {"passed": False, "message": ""},
            "buildable_area": {"passed": False, "message": ""},
            "setback": {"passed": False, "message": ""},
            "open_space": {"passed": False, "message": ""},
        },
        "violations": [],
    }

    # 1. Check site boundary
    try:
        site_poly = Polygon(site_boundary)
        if not site_poly.is_valid:
            site_poly = site_poly.buffer(0)

        candidate_poly = Polygon(candidate_boundary)
        if not candidate_poly.is_valid:
            candidate_poly = candidate_poly.buffer(0)

        if not site_poly.contains(candidate_poly):
            result["constraints"]["site_boundary"]["passed"] = False
            result["constraints"]["site_boundary"]["message"] = (
                "Rejected: building footprint crosses the confirmed site boundary."
            )
            result["violations"].append("outside_site_boundary")
            return result

        result["constraints"]["site_boundary"]["passed"] = True
        result["constraints"]["site_boundary"]["message"] = "Inside site boundary"

    except Exception as e:
        result["constraints"]["site_boundary"]["message"] = f"Error: {e}"
        return result

    # 2. Check setback compliance
    rules = setback_rules_override or sr.get_setback_rules(building_type)
    buildable_area = sr.create_buildable_area(site_boundary, setback_rules=rules)

    if buildable_area is not None:
        compliant, message = sr.check_setback_compliance(candidate_boundary, buildable_area)
        result["constraints"]["buildable_area"]["passed"] = buildable_area is not None
        result["constraints"]["setback"]["passed"] = compliant
        result["constraints"]["setback"]["message"] = message

        if not compliant:
            result["violations"].append("setback_violation")
            violation_details = sr.calculate_setback_violation(candidate_boundary, buildable_area)
            result["setback_violation_details"] = violation_details
            return result
    else:
        result["constraints"]["buildable_area"]["message"] = "No buildable area constraint"

    # 3. Check open space requirement
    open_space_pct = sr.calculate_open_space_percentage(site_boundary, candidate_boundary)
    open_space_compliant = open_space_pct >= rules.min_open_space

    result["constraints"]["open_space"]["passed"] = open_space_compliant
    result["constraints"]["open_space"]["message"] = (
        f"Open space: {open_space_pct:.1f}% (target: {rules.min_open_space}%)"
    )

    if not open_space_compliant:
        result["violations"].append("insufficient_open_space")

    # All constraints passed
    result["valid"] = len(result["violations"]) == 0

    return result


# ============================================================================
# Scoring
# ============================================================================

def score_optimization_candidate(
    candidate: dict[str, Any],
    site_boundary: list[list[float]],
    context_edges: list[dict[str, Any]] | None = None,
    site_latitude: float | None = None,
    site_longitude: float | None = None,
    selected_edge_id: str | None = None,
) -> dict[str, Any]:
    """Score an optimization candidate across multiple objectives.

    Args:
        candidate: Candidate dict with 'position' (footprint) and other data
        site_boundary: Site boundary
        context_edges: Edges from context analysis
        site_latitude: For sunlight scoring
        site_longitude: For sunlight scoring
        selected_edge_id: If user selected an edge, score edge attraction

    Returns:
        Scoring result dict with component scores and total
    """
    footprint = candidate.get("position") or candidate.get("boundary")
    if not footprint:
        return {
            "valid": False,
            "total_score": 0,
            "message": "Invalid candidate (no position/boundary)",
        }

    scores = {
        "setback_score": 0,
        "sunlight_score": 0,
        "daylight_score": 0,
        "edge_attraction_score": 0,
        "road_access_score": 50,  # Placeholder
        "open_space_score": 0,
        "density_score": 50,  # Placeholder
    }

    # Setback score (if passed validation, this is 100)
    rules = sr.get_setback_rules(None)  # Default rules for scoring
    buildable_area = sr.create_buildable_area(site_boundary, setback_rules=rules)
    if buildable_area:
        compliant, _ = sr.check_setback_compliance(footprint, buildable_area)
        scores["setback_score"] = 100 if compliant else 0
    else:
        scores["setback_score"] = 100

    # Sunlight score
    if site_latitude and site_longitude:
        try:
            sun_data = sa.get_sun_data(site_latitude, site_longitude)
            exposure = sa.calculate_sun_exposure(footprint, site_boundary, sun_data)
            scores["sunlight_score"] = exposure.get("exposure_score", 50)
        except Exception:
            scores["sunlight_score"] = 50

    # Daylight score
    if site_latitude and site_longitude:
        try:
            sun_data = sa.get_sun_data(site_latitude, site_longitude)
            daylight = sa.score_daylight(footprint, site_boundary, sun_data=sun_data)
            scores["daylight_score"] = daylight
        except Exception:
            scores["daylight_score"] = 50

    # Edge attraction score
    if selected_edge_id and context_edges:
        selected_edge_data = next(
            (e for e in context_edges if e.get("id") == selected_edge_id), None
        )
        if selected_edge_data:
            try:
                edge_meta = ebo.create_edge_metadata_from_context(selected_edge_data)
                if edge_meta:
                    scores["edge_attraction_score"] = ebo.calculate_edge_attraction_score(
                        footprint, edge_meta
                    )
            except Exception:
                pass

    # Open space score
    try:
        open_space_pct = sr.calculate_open_space_percentage(site_boundary, footprint)
        scores["open_space_score"] = min(100, open_space_pct)
    except Exception:
        scores["open_space_score"] = 50

    # Calculate weighted total
    weights = {
        "setback_score": 0.20,
        "sunlight_score": 0.20,
        "daylight_score": 0.15,
        "edge_attraction_score": 0.15 if selected_edge_id else 0.0,
        "road_access_score": 0.10,
        "open_space_score": 0.10,
        "density_score": 0.10,
    }

    # Renormalize weights if edge attraction not used
    if not selected_edge_id:
        remaining_weight = weights.pop("edge_attraction_score", 0)
        total_weight = sum(weights.values())
        if total_weight > 0:
            for key in weights:
                weights[key] = weights[key] * (1 + remaining_weight / total_weight)

    total_score = sum(scores[key] * weights.get(key, 0) for key in scores)
    total_score = min(100, max(0, total_score))

    return {
        "valid": True,
        "scores": scores,
        "weights": weights,
        "total_score": round(total_score, 1),
        "message": f"Score: {total_score:.1f}/100",
    }


# ============================================================================
# Candidate Generation
# ============================================================================

def generate_and_validate_candidates(
    boundary: list[list[float]],
    site_boundary: list[list[float]],
    num_candidates: int = 10,
    building_type: str | None = None,
    context_edges: list[dict[str, Any]] | None = None,
    site_latitude: float | None = None,
    site_longitude: float | None = None,
    selected_edge_id: str | None = None,
) -> dict[str, Any]:
    """Generate and validate optimization candidates.

    Args:
        boundary: Base building boundary
        site_boundary: Site boundary
        num_candidates: Target number of valid candidates
        building_type: Building type
        context_edges: Edges from context analysis
        site_latitude: For sunlight scoring
        site_longitude: For sunlight scoring
        selected_edge_id: If user selected an edge

    Returns:
        Result dict with valid candidates and scores
    """
    candidates = []

    # Generate candidate positions (placeholder - in real use, this comes from optimizer)
    # For now, use base position
    base_candidate = {
        "position": boundary,
        "rotation": 0,
    }

    # If edge selected, generate edge-attracted candidates
    if selected_edge_id and context_edges:
        selected_edge_data = next(
            (e for e in context_edges if e.get("id") == selected_edge_id), None
        )
        if selected_edge_data:
            try:
                edge_meta = ebo.create_edge_metadata_from_context(selected_edge_data)
                if edge_meta:
                    rules = sr.get_setback_rules(building_type)
                    buildable_area = sr.create_buildable_area(site_boundary, setback_rules=rules)
                    candidates.extend(
                        ebo.generate_candidates_near_edge(
                            site_boundary,
                            edge_meta,
                            buildable_area=buildable_area,
                            base_footprint=boundary,
                            num_candidates=num_candidates,
                        )
                    )
            except Exception as e:
                print(f"[optimization_constraints] Error generating edge-based candidates: {e}")

    # If not enough candidates, add base
    if len(candidates) < num_candidates:
        candidates.append(base_candidate)

    # Validate and score all candidates
    valid_candidates = []

    for candidate in candidates:
        footprint = candidate.get("position")
        if not footprint:
            continue

        # Validate
        validation = validate_optimization_candidate(
            footprint, site_boundary, building_type=building_type
        )

        if not validation["valid"]:
            continue

        # Score
        score_result = score_optimization_candidate(
            candidate,
            site_boundary,
            context_edges=context_edges,
            site_latitude=site_latitude,
            site_longitude=site_longitude,
            selected_edge_id=selected_edge_id,
        )

        candidate["validation"] = validation
        candidate["scoring"] = score_result
        candidate["total_score"] = score_result.get("total_score", 0)

        valid_candidates.append(candidate)

    # Sort by score
    valid_candidates.sort(key=lambda c: c.get("total_score", 0), reverse=True)

    return {
        "total_generated": len(candidates),
        "total_valid": len(valid_candidates),
        "candidates": valid_candidates[:num_candidates],
    }
