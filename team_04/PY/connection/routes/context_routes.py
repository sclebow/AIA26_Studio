"""Urban Context routes — the Context Analysis stage backend.

  POST /sessions/{id}/context        -> fetch (live Overpass) + classify + score,
                                        cache on the session, return the full payload.
                                        Body {radius_m?, refresh?}. Cached unless refresh.
  GET  /sessions/{id}/context        -> the cached context (404 if not analyzed yet).

The heavy lifting lives in notebook_logic/urban_context.py. The route only handles
caching + turning an Overpass/network failure into a clean error the UI can show.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..notebook_logic import urban_context
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["urban-context"])


class ContextRequest(BaseModel):
    radius_m: float = Field(default=urban_context.CONTEXT_RADIUS_M, ge=250, le=5000)
    refresh: bool = False
    # Allow the frontend to pass the projection origin explicitly if it isn't yet
    # persisted on the session (belt-and-braces; normally read from site_context).
    center: dict[str, float] | None = None


def _resolve_center(state: dict[str, Any], body_center: dict | None) -> dict[str, float] | None:
    if body_center and "lat" in body_center and "lng" in body_center:
        return body_center
    ctx = state.get("site_context") or {}
    c = ctx.get("center")
    if c and "lat" in c and "lng" in c:
        return c
    return None


@router.post("/{session_id}/context")
async def analyze_context(session_id: str, body: ContextRequest) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    boundary = state.get("site_boundary") or []
    if len(boundary) < 3:
        raise HTTPException(status_code=422, detail="Confirm a site boundary first")
    center = _resolve_center(state, body.center)
    if not center:
        raise HTTPException(
            status_code=422,
            detail="No geographic origin for this site — re-save the boundary so its lat/lng is recorded.",
        )

    cached = state.get("urban_context")
    if cached and not body.refresh and cached.get("radius_m") == body.radius_m:
        return {**cached, "cached": True}

    try:
        result = urban_context.analyze_context(
            [[float(p[0]), float(p[1])] for p in boundary], center, radius=body.radius_m
        )
    except Exception as exc:  # noqa: BLE001 — Overpass/network failure → clean 502
        raise HTTPException(
            status_code=502,
            detail=f"Urban context unavailable (OpenStreetMap/Overpass): {exc}",
        ) from exc

    new_state = dict(state)
    new_state["urban_context"] = result
    await store.update_state(session_id, new_state)
    return {**result, "cached": False}


@router.post("/{session_id}/context/selection")
async def store_selection(session_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Persist the user's edge/corner SELECTION (F2/F3) so context-aware prompts like
    'align to selected edge' / 'move to selected corner' can validate + use it."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    new_state = dict(state)
    if "selected_edge" in body:
        new_state["selected_edge"] = body.get("selected_edge")
    if "selected_edges" in body:
        new_state["selected_edges"] = body.get("selected_edges") or []
    if "selected_corner" in body:
        new_state["selected_corner"] = body.get("selected_corner")
    await store.update_state(session_id, new_state)
    return {"stored": True,
            "selected_edge": bool(new_state.get("selected_edge")),
            "selected_corner": bool(new_state.get("selected_corner"))}


@router.post("/{session_id}/context/store")
async def store_context(session_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Persist the urban context the FRONTEND computed (client-side via overpass.js)
    so the BACKEND can use it for context-aware shape generation. The UI was showing
    context but never sending it — this is the bridge that makes context usable design
    intelligence. Stores edges, edge_metadata, layers, scores, selected_edge, etc."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    ctx = body or {}
    # Keep a compact, structured copy: the heavy layer point-clouds are not needed for
    # edge resolution, but edges (with edge_context/nearest), scores + selected edge are.
    # Capture the geographic center (lat/lng) so environmental analysis (wind/solar
    # climate data) can look up the real site location. Accept several shapes the UI
    # might send it in.
    center = ctx.get("center") or ctx.get("site_center") or {}
    if not (isinstance(center, dict) and center.get("lat") is not None):
        loc = ctx.get("location") or {}
        if isinstance(loc, dict) and loc.get("lat") is not None:
            center = {"lat": loc.get("lat"), "lng": loc.get("lng") or loc.get("lon") or loc.get("lng")}
    stored = {
        "edges": ctx.get("edges") or [],
        "edge_metadata": ctx.get("edge_metadata") or [],
        "scores": ctx.get("scores") or ctx.get("contextScores") or {},
        "selected_edge": ctx.get("selected_edge") or ctx.get("selectedEdge"),
        "layers": ctx.get("layers") or {},
        "radius_m": ctx.get("radius") or ctx.get("radius_m"),
        "generatedAt": ctx.get("generatedAt"),
        "center": center if (isinstance(center, dict) and center.get("lat") is not None) else None,
        # Neighbouring OSM buildings (footprint + height) — used by the Density scorer to
        # compare proposed massing against the surrounding urban fabric. Capped so a dense
        # area doesn't bloat the stored state.
        "neighbor_buildings": (ctx.get("buildings") or [])[:400],
    }
    new_state = dict(state)
    new_state["urban_context"] = stored
    # Also surface lat/lng at the top level so any consumer (env_data) finds it easily.
    if isinstance(center, dict) and center.get("lat") is not None:
        new_state["site_latitude"] = float(center["lat"])
        new_state["site_longitude"] = float(center.get("lng") or center.get("lon"))
    await store.update_state(session_id, new_state)
    return {"stored": True, "edge_count": len(stored["edges"]),
            "has_scores": bool(stored["scores"])}


@router.get("/{session_id}/context")
async def get_context(session_id: str) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    ctx = state.get("urban_context")
    if not ctx:
        raise HTTPException(status_code=404, detail="No urban context analyzed for this session yet")
    return {**ctx, "cached": True}
