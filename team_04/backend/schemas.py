"""Pydantic request/response schemas for the Team 04 FastAPI backend."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class SessionCreate(BaseModel):
    layout_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Initial layout: site_boundary, building_intents, requested_positions, etc.",
    )
    max_optimization_cycles: int = Field(default=6, ge=1, le=30)


class SessionInfo(BaseModel):
    session_id: str
    created_at: str
    message_count: int
    building_count: int
    has_site: bool


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str          # "user" | "assistant"
    content: str
    message_id: str
    timestamp: str
    tags: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    tags: list[str] = Field(default_factory=list)


# SSE event types emitted by /sessions/{id}/chat stream:
# {"event": "token",   "data": "..."}          — partial LLM output
# {"event": "tool",    "data": "{name, args}"} — tool call in progress
# {"event": "state",   "data": "<state json>"} — full state after completion
# {"event": "error",   "data": "..."}          — error message
# {"event": "done",    "data": ""}             — stream finished


# ---------------------------------------------------------------------------
# Explorer tree
# ---------------------------------------------------------------------------

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
    centroid: list[float]
    height_m: float | None = None
    wings: list[WingInfo] = Field(default_factory=list)
    placement_options: list[PlacementOption] = Field(default_factory=list)
    view_score: float | None = None


class ExplorerTree(BaseModel):
    session_id: str
    site: SiteInfo | None
    buildings: list[BuildingInfo]


# ---------------------------------------------------------------------------
# Decision graph
# ---------------------------------------------------------------------------

class DecisionNodeSchema(BaseModel):
    node_id: str
    parent_id: str | None
    type: str                        # intent | action | branch | select | state
    label: str
    timestamp: str
    is_selected: bool
    payload: dict[str, Any] = Field(default_factory=dict)


class DecisionEdge(BaseModel):
    id: str
    source: str
    target: str


class DecisionGraphResponse(BaseModel):
    nodes: list[DecisionNodeSchema]
    edges: list[DecisionEdge]
    head: str | None                 # current_head node_id


# ---------------------------------------------------------------------------
# View analysis
# ---------------------------------------------------------------------------

class ViewAnalysisRequest(BaseModel):
    building_boundary: list[list[float]]
    building_height: float = 12.0
    obstacles: list[dict[str, Any]] = Field(default_factory=list)
    piece_length: float = 3.0
    floor_height: float = 3.0
    ray_length: float = 80.0


class ViewAnalysisResult(BaseModel):
    view_score_3d: float
    total_unblocked_rays: int
    total_rays: int
    n_floors: int
    per_floor: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Direct tool invocation
# ---------------------------------------------------------------------------

class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None
