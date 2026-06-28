"""Environmental Mode feature-flag routes.

Lets the UI switch between Legacy Geometry Mode and Environmental Mode at runtime
(without a restart), and inspect the cached environmental data for a site. Purely
additive — when the flag is OFF the whole environmental engine is dormant and the
optimization workflow is unchanged.

  GET  /env/mode                    -> {enabled}
  POST /env/mode      {enabled}     -> set runtime override; returns {enabled}
  GET  /sessions/{id}/env/data      -> cached env record for the session's site
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..notebook_logic.optimization import env_data as ed
from ..session_store import store

router = APIRouter(tags=["env-mode"])


class EnvModeBody(BaseModel):
    enabled: bool


@router.get("/env/mode")
async def get_env_mode() -> dict[str, Any]:
    return {"enabled": ed.env_mode_enabled()}


@router.post("/env/mode")
async def set_env_mode(body: EnvModeBody) -> dict[str, Any]:
    ed.set_env_mode(bool(body.enabled))
    return {"enabled": ed.env_mode_enabled()}


@router.get("/sessions/{session_id}/env/data")
async def get_env_data(session_id: str) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    lat, lng = ed.resolve_site_coords(state)
    rec = ed.get_site_env(lat, lng)
    return {
        "enabled": ed.env_mode_enabled(),
        "has_coordinates": lat is not None and lng is not None,
        "site": {"lat": lat, "lng": lng},
        "env": rec,
        "sources": (rec or {}).get("sources", {}),
    }
