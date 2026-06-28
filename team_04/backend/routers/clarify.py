"""Interactive clarification endpoints.

GET  /sessions/{id}/clarification        — current structured question (or null)
POST /sessions/{id}/clarify              — submit answers, resume the agent

The agent pauses (``await_human``) and stores a ``clarification_request`` in
state when a placement-critical field is missing. The UI fetches it, renders the
fields as chips, and POSTs the answers here. This endpoint merges the answers
onto the brief + layout (``agent.clarify.apply_clarification_answers``), marks the
clarification resolved, and clears the request — the next ``/chat`` turn then
continues the design with the answered values.
"""
from __future__ import annotations

import json
import sys
import os

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent.clarify import apply_clarification_answers
from ..schemas import ClarificationAnswer
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["clarify"])


@router.get("/{session_id}/clarification")
async def get_clarification(session_id: str) -> dict:
    """Return the pending clarification request, or ``{"clarification_request": null}``."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"clarification_request": state.get("clarification_request")}


@router.post("/{session_id}/clarify")
async def submit_clarification(session_id: str, body: ClarificationAnswer) -> dict:
    """Apply the user's answers and clear the pending question.

    After this returns, send a ``/chat`` message to resume the design — the agent
    now has the answered shape/side/view/size/use/count and will not re-ask.
    """
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not state.get("clarification_request"):
        raise HTTPException(status_code=409, detail="No pending clarification for this session")

    try:
        layout_payload = json.loads(state.get("layout_json", "{}"))
    except json.JSONDecodeError:
        layout_payload = {}
    if not isinstance(layout_payload, dict):
        layout_payload = {}

    site_boundary = state.get("site_boundary") or layout_payload.get("site_boundary")

    new_brief, new_layout = apply_clarification_answers(
        state.get("design_brief", {}) or {},
        layout_payload,
        body.answers,
        site_boundary,
    )

    # Persist resolved state: answered brief + enriched layout, request cleared.
    state = dict(state)
    state["design_brief"] = new_brief
    state["layout_json"] = json.dumps(new_layout)
    state["clarification_answers"] = body.answers
    state["clarification_resolved"] = True
    state["clarification_request"] = None
    if isinstance(new_layout.get("requested_positions"), list):
        state["requested_positions"] = new_layout["requested_positions"]
    if isinstance(new_layout.get("target_building_count"), int):
        state["target_building_count"] = new_layout["target_building_count"]
    await store.update_state(session_id, state)

    return {
        "resolved": True,
        "applied_answers": body.answers,
        "building_count": new_brief.get("building_count"),
        "shapes": [b.get("shape_preference") for b in new_brief.get("buildings", [])],
        "requested_positions": new_layout.get("requested_positions"),
        "view_target_sides": new_layout.get("view_target_sides"),
        "next": "POST /sessions/{id}/chat to resume the design with these values",
    }
