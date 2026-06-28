"""Site + boundary integration endpoints.

These fill the frontend's map/boundary stage, which the core agent does not expose
over HTTP. They are part of the *connection* layer (the integration bridge) — they
do NOT reimplement any agent logic. Boundary analysis, the buildable zone, and the
setback summary all delegate to the REAL agent tools:

  agent.tools.site_boundary_graph.analyze_site_boundary
  agent.tools.site_setback.compute_buildable_zone / setback_summary

Geocoding has no agent tool, so /geocode proxies the public OpenStreetMap
Nominatim service (a real geocoder). No coordinates are invented; if the proxy is
unreachable the route returns an error the frontend can fall back from.

Routes:
  POST /site/geocode                         {query}            -> {results[]}
  POST /site/boundary/analyze                {boundary}         -> graph + hierarchy
  POST /site/boundary/buildable-zone         {boundary, setback}-> buildable polygon
  POST /sessions/{id}/site/boundary          {boundary, center?}-> persists onto AgentState
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Side-effect import keeps agent.* importable regardless of CWD.
from .. import _TEAM_ROOT  # noqa: F401
from ..session_store import store

router = APIRouter(tags=["site"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class GeocodeRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=10)


class BoundaryRequest(BaseModel):
    boundary: list[list[float]] = Field(
        description="Site boundary ring as [[x|lng, y|lat], ...] (z optional)."
    )


class BuildableZoneRequest(BoundaryRequest):
    setback: float = Field(default=3.0, ge=0.0, le=100.0)


class SaveBoundaryRequest(BoundaryRequest):
    center: dict[str, float] | None = None
    location_name: str | None = None


# --------------------------------------------------------------------------- #
# Geocoding — real external geocoder proxy (no mock data)
# --------------------------------------------------------------------------- #
@router.post("/site/geocode")
def geocode(body: GeocodeRequest) -> dict[str, Any]:
    """Proxy OpenStreetMap Nominatim. Frontend keeps its own client-side geocoder
    as a fallback if this route or the upstream service is unavailable."""
    import urllib.parse
    import urllib.request
    import json as _json

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Empty geocode query")

    params = urllib.parse.urlencode(
        {"q": query, "format": "jsonv2", "limit": str(body.limit), "addressdetails": "0"}
    )
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "AIA26-Studio-Team04/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 (trusted host)
            raw = _json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Geocoder unavailable: {exc}") from exc

    results = [
        {
            "name": item.get("display_name", ""),
            "lat": float(item["lat"]),
            "lng": float(item["lon"]),
            "type": item.get("type"),
            "importance": item.get("importance"),
        }
        for item in raw
        if "lat" in item and "lon" in item
    ]
    return {"query": query, "results": results}


# --------------------------------------------------------------------------- #
# Boundary analysis — delegates to the REAL agent tools
# --------------------------------------------------------------------------- #
@router.post("/site/boundary/analyze")
def analyze_boundary(body: BoundaryRequest) -> dict[str, Any]:
    boundary = _normalize(body.boundary)
    if len(boundary) < 3:
        raise HTTPException(status_code=422, detail="Boundary needs at least 3 points")
    try:
        from agent.tools.site_boundary_graph import analyze_site_boundary

        result = analyze_site_boundary(boundary)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"boundary": boundary, "area_sqm": round(_poly_area(boundary), 2), "analysis": result}


@router.post("/site/boundary/buildable-zone")
def buildable_zone(body: BuildableZoneRequest) -> dict[str, Any]:
    boundary = _normalize(body.boundary)
    if len(boundary) < 3:
        raise HTTPException(status_code=422, detail="Boundary needs at least 3 points")
    try:
        from agent.tools.site_setback import setback_summary

        # setback_summary already returns JSON-friendly rows + the buildable
        # boundary ring (it calls compute_buildable_zone internally), so we don't
        # touch the Shapely Polygon directly here.
        summary = setback_summary(boundary, default_setback=body.setback)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "boundary": boundary,
        "setback": body.setback,
        "buildable_boundary": summary.get("buildable_boundary", []),
        "setback_summary": summary,
    }


# --------------------------------------------------------------------------- #
# Persist a confirmed boundary onto an existing session's AgentState
# --------------------------------------------------------------------------- #
@router.post("/sessions/{session_id}/site/boundary")
async def save_session_boundary(session_id: str, body: SaveBoundaryRequest) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    boundary = _normalize(body.boundary)
    if len(boundary) < 3:
        raise HTTPException(status_code=422, detail="Boundary needs at least 3 points")

    # Write the confirmed boundary into the real AgentState shape (the same field
    # build_initial_state populates). We do not recompute geometry here.
    state = dict(state)
    state["site_boundary"] = [[p[0], p[1], p[2] if len(p) > 2 else 0.0] for p in boundary]
    ctx = dict(state.get("site_context") or {})
    if body.center:
        ctx["center"] = body.center
    if body.location_name:
        ctx["location_name"] = body.location_name
    state["site_context"] = ctx
    await store.update_state(session_id, state)
    return {
        "session_id": session_id,
        "site_boundary": state["site_boundary"],
        "area_sqm": round(_poly_area(boundary), 2),
        "saved": True,
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _normalize(boundary: list[list[float]]) -> list[list[float]]:
    out: list[list[float]] = []
    for p in boundary or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            out.append([float(p[0]), float(p[1])] + ([float(p[2])] if len(p) > 2 else []))
    return out


def _poly_area(boundary: list[list[float]]) -> float:
    if not boundary or len(boundary) < 3:
        return 0.0
    pts = [(float(p[0]), float(p[1])) for p in boundary]
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(area) / 2
