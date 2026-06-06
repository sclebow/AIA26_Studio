"""Session CRUD endpoints.

POST   /sessions                  — create a new session
GET    /sessions                  — list all session IDs + metadata
GET    /sessions/{id}             — get one session's metadata
DELETE /sessions/{id}             — delete a session
GET    /sessions/{id}/state       — full AgentState snapshot
GET    /sessions/{id}/messages    — full chat history
"""
from __future__ import annotations

import sys
import os

from fastapi import APIRouter, HTTPException

# Allow importing from the agent package when running from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent.state import build_initial_state
from ..schemas import SessionCreate, SessionInfo
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=dict)
async def create_session(body: SessionCreate) -> dict:
    initial_state = build_initial_state(
        user_prompt=body.layout_payload.get("user_prompt", ""),
        layout_payload=body.layout_payload,
        max_optimization_cycles=body.max_optimization_cycles,
    )
    session_id = await store.create(initial_state)
    return {"session_id": session_id, "status": "created"}


@router.get("", response_model=list[SessionInfo])
async def list_sessions() -> list[SessionInfo]:
    ids = await store.list_ids()
    result = []
    for sid in ids:
        session = await store.get(sid)
        if not session:
            continue
        state = session["state"]
        result.append(SessionInfo(
            session_id=sid,
            created_at=session["created_at"],
            message_count=len(session["history"]),
            building_count=len(state.get("placed_buildings", [])),
            has_site=bool(state.get("site_boundary")),
        ))
    return result


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str) -> SessionInfo:
    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    state = session["state"]
    return SessionInfo(
        session_id=session_id,
        created_at=session["created_at"],
        message_count=len(session["history"]),
        building_count=len(state.get("placed_buildings", [])),
        has_site=bool(state.get("site_boundary")),
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> dict:
    ok = await store.delete(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": session_id}


@router.get("/{session_id}/state")
async def get_state(session_id: str) -> dict:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return state


@router.get("/{session_id}/messages")
async def get_messages(session_id: str) -> list:
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session["history"]
