"""Export routes for the FINAL selected option only.

  GET /sessions/{id}/export/selected/rhino  -> .3dm download
  GET /sessions/{id}/export/selected/ifc    -> Revit-compatible .ifc download

Exports ONLY the selected_final_option (set via /select-final), with the confirmed
site boundary, the selected building geometry, and floors/height/footprint/option
id/score/metadata. If no final option is selected it falls back to the first
placed building so export still works after a single generation.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..session_store import store
from . import ifc_export, rhino_export

router = APIRouter(prefix="/sessions", tags=["export-selected"])


def _poly_area(boundary: list[list[float]]) -> float:
    pts = [(float(p[0]), float(p[1])) for p in (boundary or []) if len(p) >= 2]
    if len(pts) < 3:
        return 0.0
    a = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(a) / 2.0


async def _resolve_export_inputs(session_id: str) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    site_boundary = state.get("site_boundary") or []
    if len(site_boundary) < 3:
        raise HTTPException(status_code=422, detail="No confirmed site boundary to export")

    final = state.get("selected_final_option")
    placed = state.get("placed_buildings") or []

    # Export the building the user ACTUALLY designed. The PLACED building carries the
    # real, manipulated geometry — the true outer footprint (twist/floors/move reflected),
    # any holes (courtyard) and the floor-plate stack. The selected_final_option payload
    # from the UI often carries only a generic placeholder boundary, which is why the
    # export came out as a plain box instead of the selected shape. So: PREFER the placed
    # building's real geometry; use the final option ONLY for metadata (score/use), and
    # only fall back to its boundary if there is no placed building at all.
    building_boundary = None
    building_holes: list = []
    metadata: dict[str, Any] = {}
    height_m = 12.0
    floors = 1

    if placed:
        b = placed[0]
        building_boundary = b.get("boundary") or b.get("building_boundary")
        building_holes = b.get("holes") or []
        height_m = float(b.get("height_m") or 12.0)
        floors = int(b.get("floors") or max(1, round(height_m / 3)))
        metadata = {
            "option_id": (final or {}).get("option_id") or b.get("building_id") or b.get("geometry_id"),
            "score": (final or {}).get("score"),
            "footprint_area": round(_poly_area(building_boundary or []), 1),
            "far": (final or {}).get("far"),
            "building_use": b.get("building_use") or (final or {}).get("building_use"),
            "floors": floors,
            "has_courtyard": bool(building_holes),
        }
    elif isinstance(final, dict) and final.get("boundary"):
        building_boundary = final["boundary"]
        building_holes = final.get("holes") or []
        height_m = float(final.get("height_m") or 12.0)
        floors = int(final.get("floors") or max(1, round(height_m / 3)))
        metadata = {
            "option_id": final.get("option_id"),
            "score": final.get("score"),
            "footprint_area": final.get("footprint_area") or round(_poly_area(building_boundary), 1),
            "far": final.get("far"),
            "building_use": final.get("building_use"),
            "floors": floors,
        }

    if not building_boundary or len(building_boundary) < 3:
        raise HTTPException(status_code=422, detail="No building geometry to export — generate/select one first.")

    return {
        "site_boundary": site_boundary,
        "building_boundary": building_boundary,
        "building_holes": building_holes,
        "height_m": height_m,
        "floors": floors,
        "metadata": metadata,
    }


@router.get("/{session_id}/export/selected/rhino")
async def export_selected_rhino(session_id: str) -> Response:
    args = await _resolve_export_inputs(session_id)
    try:
        data = rhino_export.export_3dm_bytes(
            site_boundary=args["site_boundary"],
            building_boundary=args["building_boundary"],
            building_holes=args.get("building_holes") or [],
            height_m=args["height_m"],
            metadata=args["metadata"],
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Rhino export failed: {exc}") from exc
    return Response(
        content=data,
        media_type="model/vnd.3dm",
        headers={"Content-Disposition": f'attachment; filename="terrapilot_{session_id[:8]}.3dm"'},
    )


@router.get("/{session_id}/export/selected/ifc")
async def export_selected_ifc(session_id: str) -> Response:
    args = await _resolve_export_inputs(session_id)
    try:
        data = ifc_export.export_ifc_bytes(
            site_boundary=args["site_boundary"],
            building_boundary=args["building_boundary"],
            height_m=args["height_m"],
            floors=args["floors"],
            metadata=args["metadata"],
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"IFC export failed: {exc}") from exc
    return Response(
        content=data,
        media_type="application/x-step",
        headers={"Content-Disposition": f'attachment; filename="terrapilot_{session_id[:8]}.ifc"'},
    )
