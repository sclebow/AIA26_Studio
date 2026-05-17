from __future__ import annotations

import json
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    user_prompt: str
    workflow_mode: str
    layout_json: str
    site_boundary: list[list[float]]
    building_intents: list[str]
    messages: list[str]
    plan: list[dict[str, str]]
    active_step_id: str | None
    current_action: str
    decision_reason: str
    pending_tool_calls: list[dict[str, Any]]
    site_context: dict[str, Any]
    shape_context: dict[str, Any]
    geometry_id: str | None
    checked_geometry_id: str | None
    placed_buildings: list[dict[str, Any]]
    remaining_candidate_positions: list[list[float]]
    requested_positions: list[list[float]]
    requested_position_assessment: dict[str, Any]
    target_building_count: int
    constraint_results: dict[str, Any]
    violations: list[str]
    evaluation_results: dict[str, Any]
    tool_history: list[dict[str, Any]]
    human_request: str | None
    final_response: str | None
    replan_required: bool
    replan_reason: str | None
    optimization_cycles: int
    max_optimization_cycles: int
    error: str | None


def build_initial_state(
    user_prompt: str,
    layout_payload: dict[str, Any] | None,
    max_optimization_cycles: int,
) -> AgentState:
    layout_payload = layout_payload or {}
    workflow_mode = str(layout_payload.get("workflow_mode", "full") or "full").strip().lower()
    if workflow_mode not in {"full", "boundary_only"}:
        workflow_mode = "full"
    requested_positions = layout_payload.get("requested_positions", [])
    building_intents = layout_payload.get("building_intents", [])
    site_boundary = layout_payload.get("site_boundary", [])
    normalized_site_boundary = [
        [float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0]
        for point in site_boundary
        if isinstance(point, (list, tuple)) and len(point) >= 2
    ]
    normalized_requested_positions = [
        [float(point[0]), float(point[1])]
        for point in requested_positions
        if isinstance(point, (list, tuple)) and len(point) >= 2
    ]
    normalized_building_intents = [
        str(intent).strip()
        for intent in building_intents
        if str(intent).strip()
    ]
    target_building_count = layout_payload.get("target_building_count")
    if not isinstance(target_building_count, int) or target_building_count < 1:
        prompt_lower = user_prompt.lower()
        target_building_count = 2 if ("two building" in prompt_lower or "2 building" in prompt_lower) else 1
    return {
        "user_prompt": user_prompt,
        "workflow_mode": workflow_mode,
        "layout_json": json.dumps(layout_payload),
        "site_boundary": normalized_site_boundary,
        "building_intents": normalized_building_intents,
        "messages": [f"User prompt: {user_prompt}"],
        "plan": [],
        "active_step_id": None,
        "current_action": "read_site",
        "decision_reason": "Initial routing.",
        "pending_tool_calls": [],
        "site_context": {},
        "shape_context": {},
        "geometry_id": None,
        "checked_geometry_id": None,
        "placed_buildings": [],
        "remaining_candidate_positions": [],
        "requested_positions": normalized_requested_positions,
        "requested_position_assessment": {},
        "target_building_count": target_building_count,
        "constraint_results": {},
        "violations": [],
        "evaluation_results": {},
        "tool_history": [],
        "human_request": None,
        "final_response": None,
        "replan_required": True,
        "replan_reason": "Initial planning required.",
        "optimization_cycles": 0,
        "max_optimization_cycles": max_optimization_cycles,
        "error": None,
    }