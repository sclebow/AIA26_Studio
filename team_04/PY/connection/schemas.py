"""Pydantic request/response schemas for the connection HTTP layer.

These describe the wire contract frontend2 consumes (frontend2/core/api.js) and
mirror the AgentState produced by the real agent (agent/state.py).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #
class SessionCreate(BaseModel):
    layout_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Initial layout: user_prompt, site_boundary, building_intents, "
        "requested_positions, target_building_count, workflow_mode.",
    )
    max_optimization_cycles: int = Field(default=6, ge=1, le=30)


class SessionInfo(BaseModel):
    session_id: str
    created_at: str
    message_count: int
    building_count: int
    has_site: bool


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    message: str
    tags: list[str] = Field(default_factory=list)


# SSE event types emitted by POST /sessions/{id}/chat:
#   token / tool / decision / state / error / done  (see routers/chat.py)


# --------------------------------------------------------------------------- #
# Explorer tree
# --------------------------------------------------------------------------- #
class SiteInfo(BaseModel):
    boundary: list[list[float]]
    area_sqm: float
    buildable_boundary: list[list[float]] | None = None
    buildable_area_sqm: float | None = None
    edge_count: int
    site_context: dict[str, Any] = Field(default_factory=dict)


class WingInfo(BaseModel):
    wing_index: int
    role: str
    area_sqm: float
    centroid: list[float]
    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    floors: int | None = None


class PlacementOption(BaseModel):
    option_id: str
    rank: int
    combined_score: float
    unblocked_view_score: float
    attractor_view_score: float
    rotation_degrees: int | float
    centroid_xy: list[float]
    boundary: list[list[float]]
    outside_area_sqm: float
    fits_within_site: bool


class BuildingInfo(BaseModel):
    building_id: str
    label: str
    building_type: str | None
    area_sqm: float
    boundary: list[list[float]]
    # Courtyard / patio voids carved by the architectural-intent layer (interior
    # rings) so the viewer can extrude the opening, not a solid block.
    holes: list[list[list[float]]] = Field(default_factory=list)
    centroid: list[float]
    height_m: float | None = None
    wings: list[WingInfo] = Field(default_factory=list)
    placement_options: list[PlacementOption] = Field(default_factory=list)
    view_score: float | None = None
    # Per-floor plate stack (each plate is an extrudable footprint at a Z height) so
    # the viewer can show per-floor edits (moved bottom floors, a taller single wing).
    floor_plates: list[dict] = Field(default_factory=list)


class ExplorerTree(BaseModel):
    session_id: str
    site: SiteInfo | None
    buildings: list[BuildingInfo]


# --------------------------------------------------------------------------- #
# Direct tool invocation
# --------------------------------------------------------------------------- #
class ToolCallRequest(BaseModel):
    tool_name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None
