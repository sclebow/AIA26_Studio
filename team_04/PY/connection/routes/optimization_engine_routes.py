"""Multi-objective optimization API — metrics, weights, and report.

These sit ALONGSIDE the existing optimize routes (session_optimize_routes,
optimization_routes). They expose the new engine's catalogue + weight controls so
the frontend can show objective metrics and let the user re-weight the blend.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..notebook_logic.optimization import (
    multi_objective_optimizer as moo,
    optimization_weights as ow,
)

router = APIRouter(prefix="/optimization", tags=["optimization-engine"])

# Human-readable catalogue of every objective + the metrics it reports.
_METRIC_CATALOGUE: dict[str, dict[str, Any]] = {
    "solar": {"label": "Solar / Daylight", "metrics": ["daylight_autonomy_pct", "udi_pct", "sun_hours", "shadow_impact", "south_facade_frac"]},
    "view": {"label": "View", "metrics": ["view_quality_score", "view_coverage_pct", "premium_view_area_pct"]},
    "road_access": {"label": "Road Access", "metrics": ["avg_distance_to_road_m", "accessibility_score", "service_efficiency"]},
    "context_response": {"label": "Context Response", "metrics": ["context_compatibility", "urban_integration_score", "street_edge_activation"]},
    "open_space": {"label": "Open Space", "metrics": ["open_space_ratio_pct", "green_coverage_pct", "public_realm_score"]},
    "wind": {"label": "Wind / Ventilation", "metrics": ["ventilation_potential", "wind_comfort_index"]},
    "density": {"label": "Density", "metrics": ["far", "far_utilization_pct", "gfa_sqm", "site_coverage_pct"]},
    "setback": {"label": "Setback Compliance", "metrics": ["compliance_pct", "buildable_envelope_utilization_pct"]},
    "walkability": {"label": "Walkability", "metrics": ["walkability_score", "transit_access_score"]},
    "privacy": {"label": "Privacy", "metrics": ["privacy_index", "overlooking_risk"]},
    "noise": {"label": "Noise", "metrics": ["noise_exposure_score", "quiet_zone_score"]},
    "construction_efficiency": {"label": "Construction Efficiency", "metrics": ["surface_to_volume_ratio", "structural_efficiency", "cost_efficiency"]},
    "structural": {"label": "Structural", "metrics": ["structural_feasibility", "lateral_stability", "slenderness_ratio"]},
    "mixed_use": {"label": "Mixed Use", "metrics": ["functional_efficiency", "use_separation_score"]},
    "emergency_access": {"label": "Emergency Access", "metrics": ["emergency_compliance_score", "fire_access_distance_m"]},
    "public_private": {"label": "Public / Private", "metrics": ["public_access_score", "semi_private_quality_score", "privacy_gradient_score", "use_conflict_score"]},
}


class WeightsRequest(BaseModel):
    weights: dict[str, float]


@router.get("/metrics")
async def list_metrics() -> dict[str, Any]:
    """Catalogue of objectives + the metrics each one reports (for the UI)."""
    return {"objectives": list(moo.SCORERS.keys()), "catalogue": _METRIC_CATALOGUE,
            "strategies": moo.STRATEGIES}


@router.get("/weights")
async def get_weights() -> dict[str, Any]:
    return {"weights": ow.get_weights(), "defaults": ow.DEFAULT_WEIGHTS}


@router.post("/weights")
async def set_weights(body: WeightsRequest) -> dict[str, Any]:
    return {"weights": ow.set_weights(body.weights)}


@router.post("/weights/reset")
async def reset_weights() -> dict[str, Any]:
    return {"weights": ow.reset_weights()}


@router.get("/report")
async def report() -> dict[str, Any]:
    """Describe what the multi-objective engine evaluates (a static methodology
    report; per-option metrics are returned by /optimize)."""
    return {
        "engine": "multi-objective site & massing optimization",
        "wraps_existing_view_optimization": True,
        "objectives": _METRIC_CATALOGUE,
        "active_weights": ow.get_weights(),
        "strategies": moo.STRATEGIES,
        "note": "Each optimize run scores valid candidates across all objectives, "
                "then returns one diverse option per strategy (Daylight/View/Density/"
                "Open Space/Wind/Balanced/Cost/Landmark).",
    }
