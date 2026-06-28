"""Design-validation routes (self-debug loop, step 3).

Exposes the deterministic ``validate_design`` tool over HTTP so the UI (or a test)
can ask "is the current building valid on this site?" and get a structured verdict.
Purely additive and READ-ONLY — it inspects the session's geometry and returns a
report; it never mutates state.

  POST /sessions/{id}/validate-design            -> verdict for the active building
  POST /sessions/{id}/validate-design/debug      -> verdict + a proposed fix (dry-run,
                                                     does NOT persist)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..notebook_logic import design_debug as dbg
from ..notebook_logic import validate_design as vd
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["validate"])


class ValidateBody(BaseModel):
    building_id: str | None = None
    expected_area: float | None = None
    max_debug_attempts: int = 3


def _building_id(b: dict[str, Any]) -> str:
    return b.get("building_id") or b.get("geometry_id") or "geometry"


def _pick(state: dict[str, Any], building_id: str | None) -> dict[str, Any] | None:
    placed = state.get("placed_buildings", []) or []
    if not placed:
        return None
    if building_id:
        return next((b for b in placed if isinstance(b, dict) and _building_id(b) == building_id), None)
    return placed[0]


@router.post("/{session_id}/validate-design")
async def validate_design_route(session_id: str, body: ValidateBody) -> dict[str, Any]:
    """Run the deterministic validator on the active building. Read-only."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    bld = _pick(state, body.building_id)
    if bld is None:
        raise HTTPException(status_code=422, detail="No building to validate — generate one first.")

    site = state.get("site_boundary")
    others = [b for b in (state.get("placed_buildings") or []) if isinstance(b, dict) and b is not bld]
    verdict = vd.validate_design(bld, site, other_buildings=others, expected_area=body.expected_area)
    return {"building_id": _building_id(bld), **verdict}


@router.post("/{session_id}/validate-design/debug")
async def validate_design_debug_route(session_id: str, body: ValidateBody) -> dict[str, Any]:
    """Validate and, if it fails, return a PROPOSED corrective fix. Dry-run: the fixed
    geometry is returned for inspection but is NOT persisted to the session."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    bld = _pick(state, body.building_id)
    if bld is None:
        raise HTTPException(status_code=422, detail="No building to validate — generate one first.")

    site = state.get("site_boundary")
    others = [b for b in (state.get("placed_buildings") or []) if isinstance(b, dict) and b is not bld]
    res = dbg.run_self_debug(bld, site, other_buildings=others,
                             expected_area=body.expected_area, max_attempts=body.max_debug_attempts)
    # strip the non-serialisable transform closure from any proposed building
    fixed = dict(res["building"])
    fixed.pop("_transform", None)
    return {
        "building_id": _building_id(bld),
        "ok": res["ok"],
        "attempts": res["attempts"],
        "log": res["log"],
        "verdict": res["verdict"],
        "proposed_building": fixed if res["attempts"] > 0 else None,
        "persisted": False,
    }
