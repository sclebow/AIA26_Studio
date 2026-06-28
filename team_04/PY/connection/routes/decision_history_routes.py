"""Decision history + final-option selection — the real project timeline.

The frontend owns the timeline (most actions happen there: picks, edits, toggles,
comparisons) and syncs each entry here so export and the decision-graph replay read
the SAME real history. Nothing is fabricated; an untouched session has an empty
history.

  POST /sessions/{id}/decision           append one decision entry
  POST /sessions/{id}/decisions/bulk     append many (batch sync)
  GET  /sessions/{id}/decision-history   the ordered timeline
  POST /sessions/{id}/select-final       mark the final selected option (for export)
  GET  /sessions/{id}/selected-final     the final option (or null)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["decision-history"])


class DecisionEntry(BaseModel):
    stage: str
    action: str
    input: Any = None
    result: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str | None = None


class BulkDecisions(BaseModel):
    entries: list[DecisionEntry]


class SelectFinalRequest(BaseModel):
    option_id: str
    option: dict[str, Any] = Field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _append(session_id: str, entries: list[DecisionEntry]) -> list[dict[str, Any]]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    history = list(state.get("decision_history") or [])
    for e in entries:
        history.append(
            {
                "step_id": f"step_{len(history) + 1:03d}",
                "timestamp": e.timestamp or _now(),
                "stage": e.stage,
                "action": e.action,
                "input": e.input,
                "result": e.result,
                "data": e.data,
            }
        )
    new_state = dict(state)
    new_state["decision_history"] = history
    await store.update_state(session_id, new_state)
    return history


@router.post("/{session_id}/decision")
async def add_decision(session_id: str, body: DecisionEntry) -> dict[str, Any]:
    history = await _append(session_id, [body])
    return {"count": len(history), "last": history[-1] if history else None}


@router.post("/{session_id}/decisions/bulk")
async def add_decisions(session_id: str, body: BulkDecisions) -> dict[str, Any]:
    history = await _append(session_id, body.entries)
    return {"count": len(history)}


@router.get("/{session_id}/decision-history")
async def get_decision_history(session_id: str) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"decision_history": state.get("decision_history") or []}


@router.post("/{session_id}/select-final")
async def select_final(session_id: str, body: SelectFinalRequest) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    new_state = dict(state)
    new_state["selected_final_option"] = {"option_id": body.option_id, **body.option}
    await store.update_state(session_id, new_state)
    # Record the selection in the timeline too.
    await _append(
        session_id,
        [DecisionEntry(stage="comparison", action="final_option_selected",
                       input=body.option_id, result="Final option chosen",
                       data={"score": body.option.get("score")})],
    )
    return {"selected_final_option": new_state["selected_final_option"]}


@router.get("/{session_id}/selected-final")
async def get_selected_final(session_id: str) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"selected_final_option": state.get("selected_final_option")}
