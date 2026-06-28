"""Export endpoints — serialize the REAL session geometry.

The core agent has no Rhino/IFC writer (only a multi-building mock), so this
connection-layer router exports exactly what the session already holds — the
placed-building boundaries and site boundary from AgentState — as GeoJSON and a
structured JSON bundle. Nothing here fabricates geometry: an empty session
exports an empty FeatureCollection.

Native .3dm / .ifc are NOT produced here (no writer exists in this repo). The
/export/{id}/rhino-mcp route forwards the real geometry to the Rhino MCP server
*if* the agent's tool client exposes a send tool; otherwise it reports that the
capability is unavailable rather than returning a fake file.

Routes:
  GET /export/{session_id}/geojson   -> FeatureCollection (download)
  GET /export/{session_id}/json      -> {site, buildings[]} bundle (download)
  POST /export/{session_id}/rhino-mcp {best_only?} -> forwards to Rhino MCP if present
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from ..session_store import store

router = APIRouter(prefix="/export", tags=["export"])


class RhinoMcpRequest(BaseModel):
    best_only: bool = False


def _ring(boundary: list | None) -> list[list[float]]:
    ring = [[float(p[0]), float(p[1])] for p in (boundary or []) if len(p) >= 2]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _building_boundary(b: dict[str, Any]) -> list:
    return b.get("boundary") or b.get("building_boundary") or []


async def _require_state(session_id: str) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return state


@router.get("/{session_id}/geojson")
async def export_geojson(session_id: str) -> Response:
    state = await _require_state(session_id)
    features: list[dict[str, Any]] = []

    site_ring = _ring(state.get("site_boundary"))
    if len(site_ring) >= 4:
        features.append({
            "type": "Feature",
            "properties": {"kind": "site_boundary"},
            "geometry": {"type": "Polygon", "coordinates": [site_ring]},
        })

    for i, b in enumerate(state.get("placed_buildings", [])):
        ring = _ring(_building_boundary(b))
        if len(ring) < 4:
            continue
        # Carry COURTYARD holes as the GeoJSON polygon's inner rings, so the exported
        # footprint matches the designed building (a courtyard reads as a real void, not
        # a solid block). Each hole is closed into a valid ring.
        rings = [ring]
        for h in (b.get("holes") or []):
            hr = _ring(h)
            if len(hr) >= 4:
                rings.append(hr)
        features.append({
            "type": "Feature",
            "properties": {
                "kind": "building",
                "building_id": b.get("building_id") or b.get("geometry_id"),
                "label": b.get("label") or f"Building {i + 1}",
                "shape_type": b.get("shape_type") or b.get("building_type"),
                "height_m": b.get("height_m"),
                "floors": b.get("floors"),
                "has_courtyard": bool(b.get("holes")),
            },
            "geometry": {"type": "Polygon", "coordinates": rings},
        })

    fc = {"type": "FeatureCollection", "features": features}
    return Response(
        content=json.dumps(fc, indent=2),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="session_{session_id[:8]}.geojson"'},
    )


@router.get("/{session_id}/json")
async def export_json(session_id: str) -> Response:
    state = await _require_state(session_id)
    bundle = {
        "session_id": session_id,
        "site_boundary": state.get("site_boundary", []),
        "site_context": state.get("site_context", {}),
        "placed_buildings": state.get("placed_buildings", []),
        "violations": state.get("violations", []),
    }
    return Response(
        content=json.dumps(bundle, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="session_{session_id[:8]}.json"'},
    )


@router.post("/{session_id}/rhino-mcp")
async def export_rhino_mcp(session_id: str, body: RhinoMcpRequest) -> JSONResponse:
    """Forward the real session geometry to the Rhino MCP server if the agent's
    tool client exposes a send/import tool. No file is fabricated."""
    state = await _require_state(session_id)
    buildings = state.get("placed_buildings", [])
    if body.best_only and buildings:
        buildings = buildings[:1]

    try:
        from ..agent_runtime import get_tool_client

        client = get_tool_client()
        tool_names = {t.get("name") if isinstance(t, dict) else getattr(t, "name", "")
                      for t in client.list_tools()}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "reason": f"Rhino MCP not reachable: {exc}"},
        )

    candidate = next((n for n in ("import_building_boundary", "send_to_rhino", "place_building")
                      if n in tool_names), None)
    if candidate is None:
        return JSONResponse(
            status_code=501,
            content={
                "status": "unsupported",
                "reason": "No Rhino export tool exposed by the tool client.",
                "available_tools": sorted(t for t in tool_names if t),
            },
        )

    try:
        results = [
            client.call_tool(candidate, {"boundary": _building_boundary(b)})
            for b in buildings
            if _building_boundary(b)
        ]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(content={"status": "sent", "tool": candidate, "count": len(results)})
