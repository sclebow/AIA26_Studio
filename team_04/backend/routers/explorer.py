"""Explorer tree endpoints — site, buildings, wings, options.

GET /sessions/{id}/explorer          — full tree (site + all buildings)
GET /sessions/{id}/site              — site boundary + buildable zone
GET /sessions/{id}/buildings         — list of buildings with metadata
GET /sessions/{id}/buildings/{b_id}  — single building detail
GET /sessions/{id}/buildings/{b_id}/options  — placement option catalog
GET /sessions/{id}/buildings/{b_id}/view     — 3D view analysis result
"""
from __future__ import annotations

import sys
import os
from typing import Any

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ..schemas import (
    BuildingInfo,
    ExplorerTree,
    ParkingZone,
    PlacementOption,
    SiteInfo,
    ViewAnalysisRequest,
    WingInfo,
)
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["explorer"])


@router.get("/{session_id}/explorer", response_model=ExplorerTree)
async def get_explorer_tree(session_id: str) -> ExplorerTree:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return ExplorerTree(
        session_id=session_id,
        site=_build_site_info(state),
        buildings=_build_building_list(state),
    )


@router.get("/{session_id}/site", response_model=SiteInfo)
async def get_site(session_id: str) -> SiteInfo:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    info = _build_site_info(state)
    if info is None:
        raise HTTPException(status_code=404, detail="No site in session")
    return info


@router.get("/{session_id}/buildings", response_model=list[BuildingInfo])
async def get_buildings(session_id: str) -> list[BuildingInfo]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _build_building_list(state)


@router.get("/{session_id}/buildings/{building_id}", response_model=BuildingInfo)
async def get_building(session_id: str, building_id: str) -> BuildingInfo:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    for info in _build_building_list(state):
        if info.building_id == building_id:
            return info
    raise HTTPException(status_code=404, detail="Building not found")


@router.get("/{session_id}/buildings/{building_id}/options",
            response_model=list[PlacementOption])
async def get_building_options(session_id: str, building_id: str) -> list[PlacementOption]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    buildings = state.get("placed_buildings", [])
    bld = next(
        (b for b in buildings if _building_id(b) == building_id), None
    )
    if bld is None:
        raise HTTPException(status_code=404, detail="Building not found")
    raw_options = bld.get("option_catalog") or bld.get("pareto_solutions") or []
    return [_coerce_option(o, i) for i, o in enumerate(raw_options)]


@router.get("/{session_id}/buildings/{building_id}/view")
async def get_building_view(
    session_id: str,
    building_id: str,
    height: float = 12.0,
    floor_height: float = 3.0,
    piece_length: float = 3.0,
    ray_length: float = 80.0,
) -> dict:
    """Run 3D view analysis on demand for a placed building."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    buildings = state.get("placed_buildings", [])
    bld = next((b for b in buildings if _building_id(b) == building_id), None)
    if bld is None:
        raise HTTPException(status_code=404, detail="Building not found")

    boundary = bld.get("boundary") or bld.get("building_boundary", [])
    if not boundary:
        raise HTTPException(status_code=422, detail="Building has no boundary")

    # Other placed buildings + site obstacles become obstacles
    other_boundaries = [
        b.get("boundary") or b.get("building_boundary", [])
        for b in buildings if _building_id(b) != building_id
    ]
    obs_with_heights = [
        {"boundary": ob, "height": float("inf")}
        for ob in other_boundaries if ob
    ]

    try:
        from agent.tools.view_3d import evaluate_building_views_3d
        result = evaluate_building_views_3d(
            boundary, height, obs_with_heights,
            piece_length=piece_length,
            floor_height=floor_height,
            ray_length=ray_length,
            return_ray_detail=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_site_info(state: dict[str, Any]) -> SiteInfo | None:
    boundary = state.get("site_boundary", [])
    if not boundary:
        return None
    ctx = state.get("site_context", {})
    area = _poly_area(boundary)
    bz_bnd = ctx.get("buildable_boundary")
    bz_area = _poly_area(bz_bnd) if bz_bnd else None

    # Phase 4 — parking zones stored in state["parking_zones"]
    raw_zones = state.get("parking_zones") or []
    parking_zones = [
        ParkingZone(
            zone_id=str(z.get("zone_id", f"parking_zone_{i}")),
            boundary=z.get("boundary", []),
            stalls_allocated=int(z.get("stalls_allocated", 0)),
            area_sqm=float(z.get("area_sqm", 0.0)),
            side_index=int(z.get("side_index", 0)),
            is_main_road_side=bool(z.get("is_main_road_side", False)),
        )
        for i, z in enumerate(raw_zones)
        if isinstance(z, dict)
    ]

    return SiteInfo(
        boundary=boundary,
        area_sqm=round(area, 2),
        buildable_boundary=bz_bnd,
        buildable_area_sqm=round(bz_area, 2) if bz_area else None,
        edge_count=max(0, len(boundary) - 1),
        site_context=ctx,
        parking_zones=parking_zones,
    )


def _build_building_list(state: dict[str, Any]) -> list[BuildingInfo]:
    buildings = state.get("placed_buildings", [])
    return [_build_building_info(b, i) for i, b in enumerate(buildings)]


def _build_building_info(bld: dict[str, Any], index: int) -> BuildingInfo:
    boundary = bld.get("boundary") or bld.get("building_boundary", [])
    area = _poly_area(boundary)
    cx, cy = _centroid(boundary)
    shape_ctx = bld.get("shape_context") or {}
    wings_raw = shape_ctx.get("wings") or bld.get("wings") or []
    wings = [
        WingInfo(
            wing_index=w.get("index", i),
            role=str(w.get("role", "wing")),
            area_sqm=round(float(w.get("area", 0)), 2),
            centroid=[round(float(c), 4) for c in w.get("centroid", [0, 0])],
        )
        for i, w in enumerate(wings_raw)
    ]
    raw_options = bld.get("option_catalog") or bld.get("pareto_solutions") or []
    options = [_coerce_option(o, i) for i, o in enumerate(raw_options)]
    return BuildingInfo(
        building_id=_building_id(bld),
        label=bld.get("label") or f"Building {index + 1}",
        building_type=bld.get("building_type") or shape_ctx.get("building_type"),
        area_sqm=round(area, 2),
        boundary=boundary,
        centroid=[round(cx, 4), round(cy, 4)],
        height_m=bld.get("height_m"),
        wings=wings,
        placement_options=options,
        view_score=bld.get("view_score"),
    )


def _coerce_option(raw: dict[str, Any], index: int) -> PlacementOption:
    return PlacementOption(
        option_id=raw.get("option_id") or f"option_{index + 1:02d}",
        rank=raw.get("rank") or (index + 1),
        combined_score=float(raw.get("combined_score", 0.0)),
        unblocked_view_score=float(raw.get("unblocked_view_score", 0.0)),
        attractor_view_score=float(raw.get("attractor_view_score", 0.0)),
        rotation_degrees=raw.get("rotation_degrees", 0),
        centroid_xy=raw.get("centroid_xy", [0.0, 0.0]),
        boundary=raw.get("boundary", []),
        outside_area_sqm=float(raw.get("outside_area_sqm", 0.0)),
        fits_within_site=bool(raw.get("fits_within_site", True)),
    )


def _building_id(bld: dict[str, Any]) -> str:
    return str(bld.get("building_id") or bld.get("geometry_id") or id(bld))


def _poly_area(boundary: list | None) -> float:
    if not boundary or len(boundary) < 3:
        return 0.0
    pts = [(float(p[0]), float(p[1])) for p in boundary]
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return abs(area) / 2


def _centroid(boundary: list | None) -> tuple[float, float]:
    if not boundary:
        return 0.0, 0.0
    xs = [float(p[0]) for p in boundary]
    ys = [float(p[1]) for p in boundary]
    return sum(xs) / len(xs), sum(ys) / len(ys)
