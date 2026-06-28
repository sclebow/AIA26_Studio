"""Geometry routes — generate / modify boundary / modify wings.

Thin wrappers over connection.notebook_logic.tool_dev_runtime.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..notebook_logic import tool_dev_runtime

router = APIRouter(prefix="/api/geometry", tags=["api-geometry"])


class GenerateRequest(BaseModel):
    area: float = Field(gt=0)
    building_type: str = "I"
    site_boundary: list[list[float]] | None = None
    optimize_placement: bool = True
    options: dict[str, Any] = Field(default_factory=dict, description="Extra generate_building_boundary kwargs.")


class ModifyRequest(BaseModel):
    geometry_id: str
    boundary: list[list[float]]
    site_boundary: list[list[float]] | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class WingsRequest(BaseModel):
    geometry_id: str
    wings: list[dict[str, Any]]
    building_graph: dict[str, Any]
    edits: list[dict[str, Any]]
    shape_type: str = "CUSTOM"
    site_boundary: list[list[float]] | None = None
    options: dict[str, Any] = Field(default_factory=dict)


@router.post("/generate")
def generate(body: GenerateRequest) -> dict[str, Any]:
    try:
        result = tool_dev_runtime.generate_geometry(
            body.area,
            building_type=body.building_type,
            site_boundary=body.site_boundary,
            optimize_placement=body.optimize_placement,
            **body.options,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"result": result, "payload": tool_dev_runtime.build_frontend_geometry_payload(result)}


@router.post("/modify")
def modify(body: ModifyRequest) -> dict[str, Any]:
    try:
        result = tool_dev_runtime.modify_geometry(
            body.geometry_id,
            body.boundary,
            site_boundary=body.site_boundary,
            **body.options,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"result": result, "payload": tool_dev_runtime.build_frontend_geometry_payload(result)}


@router.post("/wings")
def wings(body: WingsRequest) -> dict[str, Any]:
    try:
        result = tool_dev_runtime.modify_wings(
            body.geometry_id,
            body.wings,
            body.building_graph,
            body.edits,
            shape_type=body.shape_type,
            site_boundary=body.site_boundary,
            **body.options,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"result": result, "payload": tool_dev_runtime.build_frontend_geometry_payload(result)}
