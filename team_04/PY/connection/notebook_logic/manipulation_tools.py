"""Manipulation tools — the high-level apply-a-manipulation entry point that the
transform route uses. Combines part_selector (what to edit) with
geometry_transformer (how) and always validates before returning, so callers can
reject + restore on failure.

This is the reusable home for the move/rotate/scale logic that used to live only
in the dev/test geometry flow — now a proper backend module driven through the API.
"""
from __future__ import annotations

from typing import Any

from . import geometry_transformer, part_selector, tool_dev_runtime


def _unwrap(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, dict) and isinstance(result.get("data"), dict):
        return result["data"]
    return result if isinstance(result, dict) else {}


def apply_manipulation(
    building: dict[str, Any],
    *,
    part_id: str | None = None,
    dx: float = 0.0,
    dy: float = 0.0,
    rotation: float = 0.0,
    scale: float = 1.0,
    floors: int | None = None,
    height_m: float | None = None,
    site_boundary: list[list[float]] | None = None,
) -> dict[str, Any]:
    """Apply a move/rotate/scale/floors adjustment to the whole building or a selected wing,
    validate the result, and return {accepted, boundary, fits_within_site, reason?, part}.
    Never mutates the input building dict — the caller persists only on accept.

    - floors: add N floors to the building/wing (height increases by N × 3.0m)
    - height_m: set the building/wing to a specific height
    """
    part = part_selector.resolve_part(building, part_id)
    geometry_id = building.get("geometry_id") or building.get("building_id") or "geometry"

    # Wing edit → modify_building_wings (rotation / thickness).
    if part and part.get("kind") == "wing":
        edit = part_selector.wing_edit_for(part, transform={"rotation": rotation, "scale": scale})
        if not edit:
            return {"accepted": False, "reason": "No wing edit specified (set a rotation or scale)."}
        wings = building.get("wings") or []
        graph = building.get("building_graph") or {}
        if not wings or not graph:
            return {"accepted": False, "reason": "Building has no wing graph to edit."}
        result = tool_dev_runtime.modify_wings(
            geometry_id, wings, graph, [edit],
            shape_type=building.get("shape_type", "CUSTOM"), site_boundary=site_boundary,
        )
        data = _unwrap(result)
        fits = data.get("fits_within_site_boundary", True)
        new_boundary = data.get("boundary")
        if fits is False or not new_boundary:
            return {"accepted": False, "fits_within_site": False, "part": part["part_id"],
                    "reason": "Wing edit would extend outside the site boundary.",
                    "suggestion": "Try a smaller rotation or thickness change."}
        return {"accepted": True, "fits_within_site": True, "part": part["part_id"],
                "boundary": new_boundary, "wings": data.get("wings"),
                "building_graph": data.get("building_graph")}

    # Height modification (floors or height_m) — update building metadata
    if floors is not None or height_m is not None:
        new_building = dict(building)
        floor_height = 3.0  # Standard floor height in meters
        current_floors = building.get("floors") or 1
        current_height = building.get("height_m") or (current_floors * floor_height)

        if floors is not None:
            # Add N floors to current
            new_floors = max(1, current_floors + floors)
            new_height = round(new_floors * floor_height, 2)
        else:
            # Set to specific height
            new_height = round(float(height_m), 2)
            new_floors = max(1, int(new_height / floor_height))

        # For wings, update the wing data; for building, update building data
        if part and part.get("kind") == "wing":
            wing_idx = part.get("wing_index", 0)
            wings = building.get("wings") or []
            if wing_idx < len(wings):
                new_wings = [dict(w) for w in wings]
                new_wings[wing_idx] = dict(wings[wing_idx])
                new_wings[wing_idx]["floors"] = new_floors
                new_wings[wing_idx]["height_m"] = new_height
                new_building["wings"] = new_wings
                return {"accepted": True, "fits_within_site": True, "part": part["part_id"],
                        "floors": new_floors, "height_m": new_height, "building": new_building,
                        "note": f"Added {floors} floors to {part.get('label', 'wing')}"}
        else:
            # Whole building
            new_building["floors"] = new_floors
            new_building["height_m"] = new_height
            return {"accepted": True, "fits_within_site": True, "part": "building",
                    "floors": new_floors, "height_m": new_height, "building": new_building}

    # Whole-building transform → geometry_transformer (scale+translate+rotate).
    boundary = building.get("boundary") or building.get("building_boundary")
    if not boundary:
        return {"accepted": False, "reason": "Building has no boundary."}
    result = geometry_transformer.apply_transform(
        geometry_id, boundary, dx=dx, dy=dy, rotation=rotation, scale=scale, site_boundary=site_boundary,
    )
    data = _unwrap(result)
    fits = data.get("fits_within_site_boundary")
    new_boundary = data.get("transformed_boundary") or boundary
    if fits is False:
        return {"accepted": False, "fits_within_site": False, "part": "building",
                "reason": "Modification would extend outside the site boundary.",
                "suggestion": "Try a smaller move/rotation/scale, or move toward the centre.",
                "outside_area_sqm": data.get("outside_area_sqm")}
    return {"accepted": True, "fits_within_site": fits, "part": "building", "boundary": new_boundary}


def parse_and_apply(building: dict[str, Any], text: str, *, site_boundary=None) -> dict[str, Any]:
    """Parse a free-text command ("move 5m north", "add 2 floors") and apply it to the building."""
    import re

    low = (text or "").lower()

    # Check for floor addition: "add 2 floors", "add 3 stories", "+2 floors", etc.
    floors_match = re.search(r"(?:add|plus|\+)\s*(\d+)\s*(?:floors?|stor(?:eys?|ies)|levels?)", low)
    if floors_match:
        floors = int(floors_match.group(1))
        return apply_manipulation(building, floors=floors, site_boundary=site_boundary)

    # Check for specific height: "set to 45m", "height 60m", etc.
    height_match = re.search(r"(?:set to|height|make it)\s*(\d+(?:\.\d+)?)\s*m(?:eters?)?", low)
    if height_match:
        height_m = float(height_match.group(1))
        return apply_manipulation(building, height_m=height_m, site_boundary=site_boundary)

    # Fall back to existing transform parser
    cmd = geometry_transformer.parse_command(text)
    if not cmd:
        return {"accepted": False, "reason": "Could not understand the manipulation command."}
    kind = cmd.pop("kind")
    kwargs: dict[str, Any] = {"site_boundary": site_boundary}
    if kind == "move":
        kwargs.update(dx=cmd.get("dx", 0), dy=cmd.get("dy", 0))
    elif kind == "rotate":
        kwargs.update(rotation=cmd.get("rotation", 0))
    elif kind == "scale":
        kwargs.update(scale=cmd.get("scale", 1.0))
    return apply_manipulation(building, **kwargs)
