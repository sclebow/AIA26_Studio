"""Part selector — resolve a selection (whole building, a wing/arm, or a face) on
a placed building and return the geometry to manipulate.

The generator already emits per-wing geometry (wings[].boundary, role, wing_index,
centroid) and a centerline/building graph. This module reads that structure so the
manipulation tools can target a specific wing instead of only the whole building.
No geometry is reimplemented — it just indexes the existing payload.
"""
from __future__ import annotations

from typing import Any


# Friendly display names for raw wing roles, so the UI reads "Central Mass" /
# "Right Wing" instead of "connector wing". Keys match the generator's role names.
_ROLE_LABELS: dict[str, str] = {
    "connector": "Central Mass",
    "stem": "Central Mass",
    "core": "Central Mass",
    "crossbar": "Cross Wing",
    "left_wing": "Left Wing",
    "right_wing": "Right Wing",
    "north_wing": "North Wing",
    "south_wing": "South Wing",
    "east_wing": "East Wing",
    "west_wing": "West Wing",
}


def _wing_label(role: str | None) -> str:
    r = (role or "wing").lower()
    return _ROLE_LABELS.get(r, r.replace("_", " ").title())


def list_parts(building: dict[str, Any]) -> list[dict[str, Any]]:
    """Selectable parts of a building: the whole building plus each wing, with
    friendly labels (connector -> 'Central Mass', etc.)."""
    parts: list[dict[str, Any]] = [
        {
            "part_id": "building",
            "kind": "building",
            "label": "Whole building",
            "boundary": building.get("boundary") or building.get("building_boundary"),
        }
    ]
    for w in building.get("wings") or []:
        if not isinstance(w, dict):
            continue
        idx = w.get("wing_index", w.get("index"))
        parts.append(
            {
                "part_id": f"wing_{idx}",
                "kind": "wing",
                "wing_index": idx,
                "label": _wing_label(w.get("role")),
                "role": w.get("role"),
                "boundary": w.get("boundary"),
                "centroid": w.get("centroid"),
                "area_sqm": w.get("area_sqm"),
            }
        )
    return parts


def resolve_part(building: dict[str, Any], part_id: str | None) -> dict[str, Any] | None:
    """Return the selected part descriptor for part_id, defaulting to the whole
    building when part_id is missing/unknown."""
    parts = list_parts(building)
    if not part_id or part_id == "building":
        return parts[0]
    for p in parts:
        if p["part_id"] == part_id:
            return p
    # Accept a bare wing index too ("0", "1", …).
    if str(part_id).isdigit():
        for p in parts:
            if p.get("kind") == "wing" and str(p.get("wing_index")) == str(part_id):
                return p
    return parts[0]


def wing_edit_for(part: dict[str, Any], *, transform: dict[str, Any]) -> dict[str, Any] | None:
    """Translate a generic transform on a wing into a modify_building_wings `edit`
    dict (rotation/thickness). Returns None for the whole-building case (which uses
    modify_building_boundary instead)."""
    if not part or part.get("kind") != "wing":
        return None
    edit: dict[str, Any] = {"wing_index": part.get("wing_index", 0)}
    if transform.get("rotation"):
        edit["rotation_degrees"] = float(transform["rotation"])
    if transform.get("scale") and transform["scale"] != 1.0:
        edit["thickness_scale"] = float(transform["scale"])
    return edit if len(edit) > 1 else None
