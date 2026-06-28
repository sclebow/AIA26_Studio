"""Optimization routes — optimize / score / rank / objectives.

Thin wrappers over connection.notebook_logic.view_optimization_runtime.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..notebook_logic import view_optimization_runtime as vo

router = APIRouter(prefix="/api/optimize", tags=["api-optimization"])


class OptimizeRequest(BaseModel):
    boundary: list[list[float]]
    obstacles: list[list[list[float]]] = Field(default_factory=list)
    site_boundary: list[list[float]] | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class TwoBuildingRequest(BaseModel):
    boundary_1: list[list[float]]
    boundary_2: list[list[float]]
    external_obstacles: list[list[list[float]]] = Field(default_factory=list)
    site_boundary: list[list[float]] | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class RankRequest(BaseModel):
    boundary: list[list[float]]
    obstacles: list[list[list[float]]] = Field(default_factory=list)
    site_boundary: list[list[float]] | None = None
    sample_options: dict[str, Any] = Field(default_factory=dict)
    rank_options: dict[str, Any] = Field(default_factory=dict)


@router.get("/objectives")
def objectives() -> dict[str, Any]:
    return {"objectives": vo.configure_objectives()}


@router.post("")
def optimize(body: OptimizeRequest) -> dict[str, Any]:
    try:
        result = vo.optimize(
            body.boundary,
            obstacles=body.obstacles,
            site_boundary=body.site_boundary,
            **body.options,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"result": result, "payload": vo.build_optimization_payload(result)}


@router.post("/two")
def optimize_two(body: TwoBuildingRequest) -> dict[str, Any]:
    try:
        result = vo.optimize_two(
            body.boundary_1,
            body.boundary_2,
            external_obstacles=body.external_obstacles,
            site_boundary=body.site_boundary,
            **body.options,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"result": result, "payload": vo.build_optimization_payload(result)}


@router.post("/rank")
def rank(body: RankRequest) -> dict[str, Any]:
    """Sample valid placements, then rank them by view score."""
    try:
        placements = vo.sample_placements(
            body.boundary,
            site_boundary=body.site_boundary,
            **body.sample_options,
        )
        ranked = vo.rank(placements, body.obstacles, **body.rank_options)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"sampled": len(placements), "ranked": ranked}
