"""Direct tool invocation endpoints.

POST /tools/{tool_name}
    Body: {"arguments": {...}}
    Returns: tool result or error

Supported tools exposed here (add more as needed):
  view_analysis_2d     — evaluate_building_views
  view_analysis_3d     — evaluate_building_views_3d
  view_optimizer       — optimize_view_placement
  two_building_optimizer — optimize_two_building_placement
  site_setback         — compute_buildable_zone + setback_summary
  sample_placements    — sample_valid_placements
  sun_vectors          — compute_sun_vectors (worst-case preset or multi-hour)
  sun_exposure         — evaluate_sun_exposure (2D facade exposure, lower=better)
  sun_exposure_3d      — evaluate_sun_exposure_3d (per-floor mutual shading)
  worst_sun_side       — identify_worst_sun_side (worst site edge)
  site_grid            — derive_site_grid (grid aligned to a chosen side)
  aligned_placement    — optimize_aligned_placement (grid-node × aligned orient.)
  place_buildings_aligned — multi-building greedy aligned placement
  road_context         — analyze_roads (Phase 2: nearest side, main road, frontage)
  validate_road        — validate_road (normalise a single road dict)
  urban_analysis       — full_urban_analysis (Phase 2b: intersections, corner conditions, urban response)
  fetch_urban_site     — fetch_urban_site (OSM road network fetch via Overpass API)
  detect_intersections — detect_intersections_from_roads (geometry-based junction detection)
  estimate_apartments  — estimate_apartments (Phase 4: dwelling count from footprint × storeys)
  parking_demand       — parking_demand (Phase 4: stalls + area from apartment count)
  building_demand      — compute_building_demand (Phase 4: demand table for a list of buildings)
  parking_allocation   — allocate_parking_zones (Phase 4: rectangular lots near main road)
  site_entries         — propose_site_entries (Phase 5: public/private entries on the boundary)
  route_circulation    — route_internal_circulation (Phase 5: drivable corridor network)
  entrance_orientation — building_entrance_orientation (Phase 5: entrance facing access)
  fire_access          — check_fire_access (Phase 5: per-building reachability constraint)
"""
from __future__ import annotations

import sys
import os
from typing import Any

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ..schemas import ToolCallRequest, ToolCallResponse

router = APIRouter(prefix="/tools", tags=["tools"])

# Registry of directly-callable tools: name → (function, required_arg_keys)
_REGISTRY: dict[str, Any] = {}


def _lazy_registry() -> dict[str, Any]:
    """Build registry on first call so heavy imports don't slow startup."""
    if _REGISTRY:
        return _REGISTRY

    try:
        from agent.tools.view_analysis import evaluate_building_views, evaluate_attractor_views
        _REGISTRY["view_analysis_2d"] = evaluate_building_views
        _REGISTRY["attractor_view"] = evaluate_attractor_views
    except Exception:
        pass

    try:
        from agent.tools.view_3d import evaluate_building_views_3d
        _REGISTRY["view_analysis_3d"] = evaluate_building_views_3d
    except Exception:
        pass

    try:
        from agent.tools.view_optimizer import (
            optimize_view_placement,
            optimize_two_building_placement,
            sample_valid_placements,
            rank_placements_by_view,
            list_objectives,
        )
        _REGISTRY["view_optimizer"] = optimize_view_placement
        _REGISTRY["two_building_optimizer"] = optimize_two_building_placement
        _REGISTRY["sample_placements"] = sample_valid_placements
        _REGISTRY["rank_placements"] = rank_placements_by_view
        _REGISTRY["list_objectives"] = list_objectives
    except Exception:
        pass

    try:
        from agent.tools.site_setback import compute_buildable_zone, setback_summary
        _REGISTRY["buildable_zone"] = compute_buildable_zone
        _REGISTRY["setback_summary"] = setback_summary
    except Exception:
        pass

    try:
        from agent.tools.sun_analysis import (
            compute_sun_vectors,
            evaluate_sun_exposure,
            evaluate_sun_exposure_3d,
            identify_worst_sun_side,
            worst_case_sun_vector,
        )
        _REGISTRY["sun_vectors"] = compute_sun_vectors
        _REGISTRY["worst_case_sun_vector"] = worst_case_sun_vector
        _REGISTRY["sun_exposure"] = evaluate_sun_exposure
        _REGISTRY["sun_exposure_3d"] = evaluate_sun_exposure_3d
        _REGISTRY["worst_sun_side"] = identify_worst_sun_side
    except Exception:
        pass

    try:
        from agent.tools.site_grid import derive_site_grid
        from agent.tools.view_optimizer import (
            optimize_aligned_placement,
            place_buildings_aligned,
        )
        _REGISTRY["site_grid"] = derive_site_grid
        _REGISTRY["aligned_placement"] = optimize_aligned_placement
        _REGISTRY["place_buildings_aligned"] = place_buildings_aligned
    except Exception:
        pass

    try:
        from agent.tools.road_context import analyze_roads, validate_road
        _REGISTRY["road_context"] = analyze_roads
        _REGISTRY["validate_road"] = validate_road
    except Exception:
        pass

    try:
        from agent.tools.urban_analysis import (
            full_urban_analysis,
            detect_intersections_from_roads,
        )
        _REGISTRY["urban_analysis"] = full_urban_analysis
        _REGISTRY["detect_intersections"] = detect_intersections_from_roads
    except Exception:
        pass

    try:
        from agent.tools.osm_context import fetch_urban_site, fetch_or_fallback
        _REGISTRY["fetch_urban_site"] = fetch_urban_site
        _REGISTRY["fetch_or_fallback"] = fetch_or_fallback
    except Exception:
        pass

    try:
        from agent.tools.parking import (
            estimate_apartments,
            parking_demand,
            compute_building_demand,
            allocate_parking_zones,
        )
        _REGISTRY["estimate_apartments"] = estimate_apartments
        _REGISTRY["parking_demand"] = parking_demand
        _REGISTRY["building_demand"] = compute_building_demand
        _REGISTRY["parking_allocation"] = allocate_parking_zones
    except Exception:
        pass

    try:
        from agent.tools.circulation import (
            propose_site_entries,
            route_internal_circulation,
            building_entrance_orientation,
            check_fire_access,
        )
        _REGISTRY["site_entries"] = propose_site_entries
        _REGISTRY["route_circulation"] = route_internal_circulation
        _REGISTRY["entrance_orientation"] = building_entrance_orientation
        _REGISTRY["fire_access"] = check_fire_access
    except Exception:
        pass

    return _REGISTRY


@router.get("")
def list_tools() -> dict:
    return {"tools": sorted(_lazy_registry().keys())}


@router.post("/{tool_name}", response_model=ToolCallResponse)
async def call_tool(tool_name: str, body: ToolCallRequest) -> ToolCallResponse:
    registry = _lazy_registry()
    fn = registry.get(tool_name)
    if fn is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found. Available: {sorted(registry.keys())}",
        )
    try:
        result = fn(**body.arguments)
        return ToolCallResponse(tool_name=tool_name, success=True, result=result)
    except TypeError as exc:
        raise HTTPException(status_code=422, detail=f"Bad arguments: {exc}") from exc
    except Exception as exc:
        return ToolCallResponse(tool_name=tool_name, success=False, error=str(exc))
