"""Optimization constraints and validation API routes.

Exposes setback, sunlight, edge-based optimization, and validation endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..notebook_logic import edge_based_optimizer as ebo
from ..notebook_logic import optimization_constraints as oc
from ..notebook_logic import setback_rules as sr
from ..notebook_logic import sunlight_analysis as sa

router = APIRouter(prefix="/api/constraints", tags=["api-constraints"])


# ============================================================================
# Request Models
# ============================================================================

class ValidateRequest(BaseModel):
    candidate_boundary: list[list[float]]
    site_boundary: list[list[float]]
    building_type: str | None = None


class ScoreRequest(BaseModel):
    candidate_boundary: list[list[float]]
    site_boundary: list[list[float]]
    building_type: str | None = None
    context_edges: list[dict[str, Any]] | None = None
    site_latitude: float | None = None
    site_longitude: float | None = None
    selected_edge_id: str | None = None


class SetbackRequest(BaseModel):
    site_boundary: list[list[float]]
    building_type: str | None = None


class SunlightRequest(BaseModel):
    building_footprint: list[list[float]]
    site_boundary: list[list[float]]
    site_latitude: float
    site_longitude: float


class EdgeAttractionRequest(BaseModel):
    building_footprint: list[list[float]]
    selected_edge_id: str
    context_edges: list[dict[str, Any]]


class OptimizeCandidatesRequest(BaseModel):
    boundary: list[list[float]]
    site_boundary: list[list[float]]
    building_type: str | None = None
    num_candidates: int = 10
    context_edges: list[dict[str, Any]] | None = None
    site_latitude: float | None = None
    site_longitude: float | None = None
    selected_edge_id: str | None = None


# ============================================================================
# Routes
# ============================================================================

@router.get("/setback-rules")
def get_setback_rules_endpoint(building_type: str | None = None) -> dict[str, Any]:
    """Get setback rules for a building type."""
    rules = sr.get_setback_rules(building_type)
    return {
        "building_type": building_type or "default",
        "rules": {
            "front_setback": rules.front_setback,
            "rear_setback": rules.rear_setback,
            "side_setback": rules.side_setback,
            "min_open_space": rules.min_open_space,
            "description": rules.description,
        },
    }


@router.post("/validate")
def validate_candidate(body: ValidateRequest) -> dict[str, Any]:
    """Validate a candidate building against constraints."""
    try:
        result = oc.validate_optimization_candidate(
            body.candidate_boundary,
            body.site_boundary,
            building_type=body.building_type,
        )
        return {"validation": result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/score")
def score_candidate(body: ScoreRequest) -> dict[str, Any]:
    """Score a candidate building across multiple objectives."""
    try:
        candidate = {
            "position": body.candidate_boundary,
            "rotation": 0,
        }

        result = oc.score_optimization_candidate(
            candidate,
            body.site_boundary,
            context_edges=body.context_edges,
            site_latitude=body.site_latitude,
            site_longitude=body.site_longitude,
            selected_edge_id=body.selected_edge_id,
        )
        return {"scoring": result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sunlight-analysis")
def analyze_sunlight(body: SunlightRequest) -> dict[str, Any]:
    """Analyze sunlight exposure of a building."""
    try:
        sun_data = sa.get_sun_data(body.site_latitude, body.site_longitude)

        exposure = sa.calculate_sun_exposure(
            body.building_footprint,
            body.site_boundary,
            sun_data,
        )

        seasonal = sa.calculate_seasonal_exposure(
            body.building_footprint,
            body.site_boundary,
            body.site_latitude,
            body.site_longitude,
        )

        daylight_score = sa.score_daylight(
            body.building_footprint,
            body.site_boundary,
            sun_data=sun_data,
        )

        return {
            "sun_data": {
                "date": sun_data.date.isoformat(),
                "sunrise": sun_data.sunrise.isoformat(),
                "sunset": sun_data.sunset.isoformat(),
                "day_length_hours": sun_data.day_length_hours,
            },
            "exposure": exposure,
            "seasonal": seasonal,
            "daylight_score": daylight_score,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/edge-attraction")
def calculate_edge_attraction(body: EdgeAttractionRequest) -> dict[str, Any]:
    """Calculate edge attraction score for a building."""
    try:
        selected_edge_data = next(
            (e for e in body.context_edges if e.get("id") == body.selected_edge_id),
            None,
        )

        if not selected_edge_data:
            raise ValueError(f"Edge {body.selected_edge_id} not found")

        edge_meta = ebo.create_edge_metadata_from_context(selected_edge_data)
        if not edge_meta:
            raise ValueError("Invalid edge metadata")

        score = ebo.calculate_edge_attraction_score(body.building_footprint, edge_meta)

        return {
            "selected_edge_id": body.selected_edge_id,
            "selected_edge_label": edge_meta.label,
            "edge_attraction_score": score,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/optimize-candidates")
def optimize_candidates(body: OptimizeCandidatesRequest) -> dict[str, Any]:
    """Generate and validate optimization candidates."""
    try:
        result = oc.generate_and_validate_candidates(
            body.boundary,
            body.site_boundary,
            num_candidates=body.num_candidates,
            building_type=body.building_type,
            context_edges=body.context_edges,
            site_latitude=body.site_latitude,
            site_longitude=body.site_longitude,
            selected_edge_id=body.selected_edge_id,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/health")
def constraints_health() -> dict[str, Any]:
    """Health check for constraint modules."""
    return {
        "status": "ok",
        "modules": [
            "setback_rules",
            "sunlight_analysis",
            "edge_based_optimizer",
            "optimization_constraints",
        ],
    }
