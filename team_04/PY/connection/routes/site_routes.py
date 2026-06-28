"""Site routes — confirm / load / clear the shared site of truth.

Thin wrappers over connection.notebook_logic.site_state.
"""
from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..notebook_logic import site_state

router = APIRouter(prefix="/api/site", tags=["api-site"])

# Edge selection state file
_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
_EDGE_STATE_PATH = os.path.join(_DATA_DIR, "selected_edge.json")


class ConfirmSiteRequest(BaseModel):
    boundary: list[list[float]] = Field(description="Ring of [x,y] meters, or [lng,lat] if project=true.")
    project: bool = Field(default=False, description="If true, treat boundary as lng/lat and project to meters.")
    location_name: str | None = None
    origin: dict[str, float] | None = None


class SelectEdgeRequest(BaseModel):
    edge_id: str | None = Field(description="ID of the edge to select, or null to deselect")
    edge_data: dict[str, Any] | None = Field(default=None, description="Full edge metadata for optimization")


@router.post("/confirm")
def confirm_site(body: ConfirmSiteRequest) -> dict[str, Any]:
    try:
        record = site_state.save_confirmed_site(
            body.boundary,
            project=body.project,
            location_name=body.location_name,
            origin=body.origin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"saved": True, "site": record}


@router.get("/confirmed")
def get_confirmed_site() -> dict[str, Any]:
    record = site_state.load_confirmed_site()
    return {"has_site": record is not None, "site": record}


@router.delete("/confirmed")
def clear_site() -> dict[str, Any]:
    return {"cleared": site_state.clear_confirmed_site()}


@router.post("/select-edge")
def select_edge(body: SelectEdgeRequest) -> dict[str, Any]:
    """Select a site edge for optimization."""
    os.makedirs(_DATA_DIR, exist_ok=True)

    if body.edge_id is None:
        # Deselect edge
        if os.path.exists(_EDGE_STATE_PATH):
            os.remove(_EDGE_STATE_PATH)
        return {"selected_edge_id": None, "deselected": True}

    # Save selected edge
    state = {
        "edge_id": body.edge_id,
        "edge_data": body.edge_data or {},
    }
    with open(_EDGE_STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)

    return {"selected_edge_id": body.edge_id, "saved": True}


@router.get("/selected-edge")
def get_selected_edge() -> dict[str, Any]:
    """Get the currently selected edge for optimization."""
    if not os.path.exists(_EDGE_STATE_PATH):
        return {"selected_edge_id": None, "edge_data": None}

    try:
        with open(_EDGE_STATE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data
    except (json.JSONDecodeError, OSError):
        return {"selected_edge_id": None, "edge_data": None}
