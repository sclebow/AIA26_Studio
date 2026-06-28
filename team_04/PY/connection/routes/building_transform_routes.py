"""Building transform routes — move / rotate a placed building.

The viewer's Move/Rotate tools call these directly with concrete values, instead
of relying on the LLM to interpret vague chat text. The actual geometry transform
is the EXISTING tool agent.tools.modify_building_boundary (same one the agent's
optimize step uses) — no transform math is reimplemented. The transformed boundary
is written back into the session's placed_buildings so /explorer re-renders it.

  POST /sessions/{id}/buildings/{building_id}/transform
       {translate_by_xy?: [dx,dy], rotation_degrees?: float}
       -> {building_id, boundary, fits_within_site}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..notebook_logic import tool_dev_runtime
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["building-transform"])


class TransformRequest(BaseModel):
    translate_by_xy: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    rotation_degrees: float = 0.0
    # Uniform scale about the building centroid (1.0 = no change). Scale is not a
    # native modify_building_boundary op, so we scale the ring then revalidate the
    # site fit through modify_building_boundary (translate=0).
    scale: float = 1.0
    # Which part to transform: "building" (default) or "wing_<index>". Wings are
    # transformed through modify_building_wings (rotation/thickness).
    part_id: str | None = None


def _building_id(bld: dict[str, Any]) -> str:
    return str(bld.get("building_id") or bld.get("geometry_id") or id(bld))


def _scale_about_centroid(boundary: list[list[float]], factor: float) -> list[list[float]]:
    pts = [p for p in boundary if isinstance(p, (list, tuple)) and len(p) >= 2]
    if not pts or factor == 1.0:
        return boundary
    cx = sum(float(p[0]) for p in pts) / len(pts)
    cy = sum(float(p[1]) for p in pts) / len(pts)
    out = []
    for p in boundary:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            z = [float(p[2])] if len(p) > 2 else []
            out.append([cx + (float(p[0]) - cx) * factor, cy + (float(p[1]) - cy) * factor] + z)
        else:
            out.append(p)
    return out


def _unwrap(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, dict) and isinstance(result.get("data"), dict):
        return result["data"]
    return result if isinstance(result, dict) else {}


def _poly_area(boundary) -> float:
    pts = [(float(p[0]), float(p[1])) for p in (boundary or []) if len(p) >= 2]
    if len(pts) < 3:
        return 0.0
    a = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(a) / 2.0


def _validate_transformed(new_boundary, site_boundary, data: dict[str, Any]) -> dict[str, Any]:
    """Validate a temporary transformed footprint. Returns {valid, reason}.
    Conservative: an UNKNOWN fit is treated as invalid so the building can never be
    moved outside (or vanish) without a positive in-site confirmation."""
    # 1. Non-degenerate polygon (guards against the "building disappears" case).
    if not new_boundary or len(new_boundary) < 3 or _poly_area(new_boundary) < 1.0:
        return {"valid": False, "reason": "the resulting footprint is invalid (degenerate geometry)."}

    # 2. Must have a confirmed site to validate against.
    if not site_boundary or len(site_boundary) < 3:
        return {"valid": False, "reason": "no confirmed site boundary to validate against."}

    # 3. Site fit — require an explicit True. None/False → reject.
    fits = data.get("fits_within_site_boundary")
    if fits is not True:
        outside = data.get("outside_area_sqm")
        if outside is None:
            # Derive the outside area when the tool didn't report it.
            try:
                from shapely.geometry import Polygon
                bp = Polygon([(p[0], p[1]) for p in new_boundary])
                sp = Polygon([(p[0], p[1]) for p in site_boundary])
                outside = round(bp.difference(sp).area, 1) if bp.is_valid and sp.is_valid else None
            except Exception:  # noqa: BLE001
                outside = None
        detail = f" The building extends {outside} m² outside the site boundary." if outside else \
                 " The building would extend outside the site boundary."
        return {"valid": False, "reason": "the modification leaves the confirmed site." + detail}

    # 4. Self-intersection / boundary crossing reported by the tool.
    if data.get("boundary_intersects_site_boundary"):
        return {"valid": False, "reason": "the footprint crosses the site boundary / setback zone."}

    return {"valid": True, "reason": ""}


@router.get("/{session_id}/buildings/{building_id}/parts")
async def list_building_parts(session_id: str, building_id: str) -> dict[str, Any]:
    """Selectable parts of a building (whole building + each wing) so the viewer
    can offer wing/arm selection."""
    from ..notebook_logic import part_selector

    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    placed = state.get("placed_buildings", []) or []
    bld = next((b for b in placed if isinstance(b, dict) and _building_id(b) == building_id), None)
    if bld is None:
        raise HTTPException(status_code=404, detail="Building not found")
    return {"building_id": building_id, "parts": part_selector.list_parts(bld)}


@router.post("/{session_id}/buildings/{building_id}/transform")
async def transform_building(
    session_id: str, building_id: str, body: TransformRequest
) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    placed = list(state.get("placed_buildings", []) or [])
    idx = next(
        (i for i, b in enumerate(placed) if isinstance(b, dict) and _building_id(b) == building_id),
        None,
    )
    if idx is None:
        raise HTTPException(status_code=404, detail="Building not found in session")

    bld = dict(placed[idx])
    boundary = bld.get("boundary") or bld.get("building_boundary")
    geometry_id = bld.get("geometry_id") or building_id
    if not boundary:
        raise HTTPException(status_code=422, detail="Building has no boundary to transform")

    site_boundary = state.get("site_boundary") or None

    # Wing-level edit: modify_building_wings only supports per-wing ROTATION and
    # THICKNESS (scale) — there is no per-wing translation (you can't slide one arm
    # of a connected shape without breaking the wing graph). So a MOVE on a wing is
    # applied to the WHOLE building instead; rotation/scale go to the wing tool.
    is_move = (
        len(body.translate_by_xy) >= 2
        and (body.translate_by_xy[0] or body.translate_by_xy[1])
        and not body.rotation_degrees
        and (not body.scale or body.scale == 1.0)
    )
    if body.part_id and body.part_id != "building" and not is_move:
        return await _transform_wing(session_id, state, placed, idx, bld, body, site_boundary)
    # (a wing MOVE falls through to the whole-building transform below)

    translate = (
        [float(body.translate_by_xy[0]), float(body.translate_by_xy[1])]
        if len(body.translate_by_xy) >= 2
        else [0.0, 0.0]
    )

    # Apply uniform scale first (about the centroid), then let the geometry tool
    # apply translate/rotate AND revalidate the site fit on the scaled ring.
    working_boundary = _scale_about_centroid(boundary, float(body.scale))

    try:
        # modify_geometry forwards **kwargs straight to modify_building_boundary,
        # so pass the transform params directly (not nested under "options").
        result = tool_dev_runtime.modify_geometry(
            geometry_id,
            working_boundary,
            site_boundary=site_boundary,
            translate_by_xy=translate,
            rotation_degrees=float(body.rotation_degrees),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    data = _unwrap(result)
    new_boundary = data.get("transformed_boundary") or working_boundary

    # STRICT validation: validate the temporary geometry against the confirmed site
    # before accepting. Reject (and keep the previous valid design) if the fit is
    # False OR UNKNOWN (None — e.g. no site boundary was checked), if the polygon is
    # degenerate, or if it intersects the boundary. Unknown == reject, never silently
    # accept — that was letting buildings move outside / disappear.
    verdict = _validate_transformed(new_boundary, site_boundary, data)
    if not verdict["valid"]:
        op = "scale" if (body.scale and body.scale != 1.0) else ("rotation" if body.rotation_degrees else "move")
        suggestion = {
            "scale": "Try a smaller scale, or move the building toward the site centre first.",
            "rotation": "Try a smaller rotation angle.",
            "move": "Try a smaller move, or move toward the site centre.",
        }[op]
        return {
            "building_id": building_id,
            "boundary": boundary,  # unchanged — previous valid geometry restored
            "fits_within_site": False,
            "rejected": True,
            "reason": f"Manipulation rejected. Reason: {verdict['reason']}",
            "suggestion": suggestion,
            "translate_by_xy": body.translate_by_xy,
            "rotation_degrees": body.rotation_degrees,
            "scale": body.scale,
        }
    fits = True

    # Accepted: write the new boundary back so the explorer and viewer re-render.
    bld["boundary"] = new_boundary
    # Rebuild the per-floor plate stack from the NEW footprint so a scale/rotate is
    # actually visible — the viewer draws the plate stack when present, so without
    # this the building would keep its OLD size on screen even though the boundary
    # changed. Preserve the floor count + floor height; re-stack on the new ring.
    if bld.get("floor_plates"):
        try:
            from ..notebook_logic import floor_plates as fpl

            old_plates = bld["floor_plates"]
            fh = (old_plates[0].get("height") if old_plates else None) or 3.0
            bld["floor_plates"] = fpl.build_floor_plates(
                new_boundary, len(old_plates), floor_height=fh, wings=bld.get("wings"),
            )
        except Exception:  # noqa: BLE001
            pass  # keep old plates rather than crash the transform
    placed[idx] = bld
    new_state = dict(state)
    new_state["placed_buildings"] = placed
    await store.update_state(session_id, new_state)

    return {
        "building_id": building_id,
        "boundary": new_boundary,
        "fits_within_site": fits,
        "rejected": False,
        "translate_by_xy": body.translate_by_xy,
        "rotation_degrees": body.rotation_degrees,
        "scale": body.scale,
    }


async def _transform_wing(session_id, state, placed, idx, bld, body, site_boundary):
    """Edit a single wing via modify_building_wings (rotation / thickness scale),
    validate, and only persist if it still fits the site."""
    from ..notebook_logic import part_selector, tool_dev_runtime

    part = part_selector.resolve_part(bld, body.part_id)
    if not part or part.get("kind") != "wing":
        raise HTTPException(status_code=422, detail="Selected part is not a wing")

    transform = {"rotation": body.rotation_degrees, "scale": body.scale}
    edit = part_selector.wing_edit_for(part, transform=transform)
    if not edit:
        raise HTTPException(status_code=422, detail="No wing edit (set a rotation or scale)")

    geometry_id = bld.get("geometry_id") or _building_id(bld)
    wings = bld.get("wings") or []
    building_graph = bld.get("building_graph") or {}
    if not wings or not building_graph:
        raise HTTPException(status_code=422, detail="Building has no wing graph to edit")

    try:
        result = tool_dev_runtime.modify_wings(
            geometry_id, wings, building_graph, [edit],
            shape_type=bld.get("shape_type", "CUSTOM"), site_boundary=site_boundary,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    data = _unwrap(result)
    new_boundary = data.get("boundary")
    verdict = _validate_transformed(new_boundary, site_boundary, data)
    if not verdict["valid"]:
        return {
            "building_id": _building_id(bld),
            "boundary": bld.get("boundary"),  # keep previous valid geometry
            "rejected": True,
            "fits_within_site": False,
            "reason": f"Manipulation rejected. Reason: {verdict['reason']}",
            "suggestion": "Try a smaller rotation or thickness change for this wing.",
            "part_id": body.part_id,
        }
    fits = True

    bld["boundary"] = new_boundary
    if data.get("wings"):
        bld["wings"] = data["wings"]
    if data.get("building_graph"):
        bld["building_graph"] = data["building_graph"]
    placed[idx] = bld
    new_state = dict(state)
    new_state["placed_buildings"] = placed
    await store.update_state(session_id, new_state)
    return {
        "building_id": _building_id(bld),
        "boundary": new_boundary,
        "fits_within_site": fits,
        "rejected": False,
        "part_id": body.part_id,
        "rotation_degrees": body.rotation_degrees,
        "scale": body.scale,
    }
