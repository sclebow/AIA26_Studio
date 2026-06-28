"""Shape-selection route — STAGE 2 of the workflow.

The frontend's Shape Library (Stage 1) shows the typology options produced by
/generate-options. When the user picks ONE, this route promotes that shape into
the session's single `placed_buildings` entry, so every downstream stage
(optimize / transform / architectural-feedback / export) operates on the chosen
shape. No optimization runs here — selection only.

  POST /sessions/{id}/select-shape  {option_id}
       -> {building_id, shape_type, boundary, floors, height_m}

The chosen shape is found in state["generated_options"] (persisted by
generate_options_routes). This keeps the backend the source of truth for which
shape is placed, instead of the frontend silently inventing a building.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["shape-selection"])


class SelectShapeRequest(BaseModel):
    option_id: str


@router.post("/{session_id}/select-shape")
async def select_shape(session_id: str, body: SelectShapeRequest) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    generated = state.get("generated_options") or []
    opt = next((o for o in generated if isinstance(o, dict) and o.get("option_id") == body.option_id), None)
    if opt is None:
        raise HTTPException(status_code=404, detail="Shape option not found in this session")

    boundary = opt.get("footprint") or opt.get("boundary")
    if not boundary or len(boundary) < 3:
        raise HTTPException(status_code=422, detail="Selected shape has no usable footprint")

    building_id = opt["option_id"]
    placed_building = {
        "building_id": building_id,
        "geometry_id": building_id,
        "boundary": boundary,
        "shape_type": opt.get("shape_type"),
        "building_type": opt.get("shape_type"),
        "floors": opt.get("floors"),
        "height_m": opt.get("height_m"),
        "building_use": opt.get("building_use"),
        # Carry the wings + building graph so per-wing floor edits ("add 2 floors on
        # the right wing") can target a single wing instead of the whole building.
        "wings": opt.get("wings") or [],
        "building_graph": opt.get("building_graph") or {},
        # carry the site-fit summary so transform/feedback validation has context.
        "site_fit_summary": opt.get("validation_report") or {},
    }

    # Pre-build the per-floor plate stack so floor-level manipulation works straight
    # away (each plate is an extrudable footprint at a Z height; see floor_plates.py).
    try:
        from ..notebook_logic import floor_plates as fpl

        placed_building["floor_plates"] = fpl.build_floor_plates(
            boundary,
            int(placed_building["floors"] or 1),
            wings=placed_building["wings"],
        )
    except Exception:  # noqa: BLE001
        placed_building["floor_plates"] = []

    new_state = dict(state)
    # Single selected shape becomes THE placed building (replaces any prior one).
    new_state["placed_buildings"] = [placed_building]
    new_state["selected_shape_option_id"] = building_id
    await store.update_state(session_id, new_state)

    return {
        "building_id": building_id,
        "shape_type": placed_building["shape_type"],
        "boundary": boundary,
        "floors": placed_building["floors"],
        "height_m": placed_building["height_m"],
        "wings": [w.get("role") for w in placed_building["wings"]],
    }
