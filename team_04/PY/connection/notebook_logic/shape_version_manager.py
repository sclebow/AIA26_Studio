"""Shape version manager — save the current manipulated building as a new option.

Sits above design_option_store. Captures the live building geometry (boundary +
holes + floor plates + floors/height + wings) plus its accumulated manipulation
history, and saves it as a NEW Shape Library version with a parent pointer. Never
overwrites; each save is a new shape_option_id.
"""
from __future__ import annotations

from typing import Any

from . import design_option_store as store


def capture_geometry(bld: dict[str, Any]) -> dict[str, Any]:
    """Snapshot the building's current geometry for saving."""
    return {
        "boundary": bld.get("boundary") or bld.get("building_boundary"),
        "holes": bld.get("holes") or [],
        "floor_plates": bld.get("floor_plates") or [],
        "floors": bld.get("floors"),
        "height_m": bld.get("height_m"),
        "wings": bld.get("wings") or [],
        "building_graph": bld.get("building_graph") or {},
        "shape_type": bld.get("shape_type") or bld.get("building_type"),
        "building_use": bld.get("building_use"),
    }


def save_version(
    state: dict[str, Any],
    bld: dict[str, Any],
    *,
    created_from_prompt: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Save the building's current geometry as a NEW design option version.

    The parent is the most-recently-saved option for this building's lineage (or
    the building's own original option id when this is the first save). Returns the
    new option record (already appended to state['design_options'])."""
    geometry = capture_geometry(bld)
    shape_type = geometry.get("shape_type")

    # Parent = the last saved version in this lineage, else the building's id.
    existing = store.list_options(state)
    parent = existing[-1]["shape_option_id"] if existing else (
        bld.get("source_shape_option_id") or bld.get("building_id")
    )

    history = list(bld.get("manipulation_history") or [])
    option = store.make_option(
        state=state,
        geometry=geometry,
        shape_type=shape_type,
        parent_option_id=parent,
        manipulation_history=history,
        created_from_prompt=created_from_prompt,
        label=label,
    )
    store.add_option(state, option)
    return option


def record_manipulation(bld: dict[str, Any], *, prompt: str, operation: str,
                        target_part: str | None) -> None:
    """Append one manipulation to the building's in-progress history (Fix 3/4).
    This history travels with a save into the option's manipulation_history."""
    hist = list(bld.get("manipulation_history") or [])
    hist.append({"prompt": prompt, "op": operation, "target_part": target_part,
                 "text": f"{operation} on {target_part or 'building'}"})
    bld["manipulation_history"] = hist


def list_versions(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Shape Library rows: id, parent, type, label, created_at — geometry omitted."""
    return [
        {k: v for k, v in o.items() if k != "geometry"}
        for o in store.list_options(state)
    ]
