"""Direct tool invocation — exposes the REAL agent.tools functions over HTTP.

GET  /tools              — list callable tool names
POST /tools/{tool_name}  — call a tool  {tool_name, arguments} -> {success, result|error}

The registry imports the actual agent.tools.* functions (view analysis, view
optimizer, setbacks). No tool logic is reimplemented here.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..schemas import ToolCallRequest, ToolCallResponse

router = APIRouter(prefix="/tools", tags=["tools"])

_REGISTRY: dict[str, Any] = {}


def _lazy_registry() -> dict[str, Any]:
    if _REGISTRY:
        return _REGISTRY

    try:
        from agent.tools.view_analysis import evaluate_attractor_views, evaluate_building_views
        _REGISTRY["view_analysis_2d"] = evaluate_building_views
        _REGISTRY["attractor_view"] = evaluate_attractor_views
    except Exception:  # noqa: BLE001
        pass

    try:
        from agent.tools.view_3d import evaluate_building_views_3d
        _REGISTRY["view_analysis_3d"] = evaluate_building_views_3d
    except Exception:  # noqa: BLE001
        pass

    try:
        from agent.tools.view_optimizer import (
            list_objectives,
            optimize_two_building_placement,
            optimize_view_placement,
            rank_placements_by_view,
            sample_valid_placements,
        )
        _REGISTRY["view_optimizer"] = optimize_view_placement
        _REGISTRY["two_building_optimizer"] = optimize_two_building_placement
        _REGISTRY["sample_placements"] = sample_valid_placements
        _REGISTRY["rank_placements"] = rank_placements_by_view
        _REGISTRY["list_objectives"] = list_objectives
    except Exception:  # noqa: BLE001
        pass

    try:
        from agent.tools.site_setback import compute_buildable_zone, setback_summary
        _REGISTRY["buildable_zone"] = compute_buildable_zone
        _REGISTRY["setback_summary"] = setback_summary
    except Exception:  # noqa: BLE001
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
    except Exception as exc:  # noqa: BLE001
        return ToolCallResponse(tool_name=tool_name, success=False, error=str(exc))
