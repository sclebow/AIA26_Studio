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
