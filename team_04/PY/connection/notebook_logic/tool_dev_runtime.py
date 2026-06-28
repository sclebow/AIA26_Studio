"""Geometry runtime — generate/modify building geometry and shape payload helpers.

Thin wrappers over the EXISTING geometry tools. No geometry math is reimplemented:

    agent.tools.generate_building_boundary.generate_building_boundary
    agent.tools.modify_building_boundary.modify_building_boundary
    agent.tools.modify_building_wings.modify_building_wings

The extraction helpers (centerline graph, wing metadata, frontend payload) pull
fields straight out of those tools' own output dicts.

Used by:
  * connection/routes/geometry_routes.py  (/api/geometry/*)  -> frontend editing
  * test_notebooks/tool_dev_mode.ipynb                       -> validation
"""
from __future__ import annotations

from typing import Any

from . import site_state

from agent.tools.generate_building_boundary import generate_building_boundary
from agent.tools.modify_building_boundary import modify_building_boundary
from agent.tools.modify_building_wings import modify_building_wings


def _unwrap(result: dict[str, Any]) -> dict[str, Any]:
    """Tools return {success, data, metadata}; return the inner data dict."""
    if isinstance(result, dict) and isinstance(result.get("data"), dict):
        return result["data"]
    return result if isinstance(result, dict) else {}


def _resolve_site_boundary(site_boundary: list[list[float]] | None) -> list[list[float]] | None:
    if site_boundary:
        return site_boundary
    return site_state.load_confirmed_boundary()


# --------------------------------------------------------------------------- #
# Generate / modify
# --------------------------------------------------------------------------- #
def generate_geometry(
    area: float,
    *,
    building_type: str = "I",
    site_boundary: list[list[float]] | None = None,
    optimize_placement: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate a building boundary. Falls back to the confirmed site when no
    explicit site_boundary is given, so generated geometry lands inside it."""
    return generate_building_boundary(
        area=area,
        building_type=building_type,
        site_boundary=_resolve_site_boundary(site_boundary),
        optimize_placement=optimize_placement,
        **kwargs,
    )


def modify_geometry(
    geometry_id: str,
    boundary: list[list[float]],
    *,
    site_boundary: list[list[float]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Translate / rotate / mirror / align an existing building boundary."""
    return modify_building_boundary(
        geometry_id=geometry_id,
        boundary=boundary,
        site_boundary=_resolve_site_boundary(site_boundary),
        **kwargs,
    )


def modify_wings(
    geometry_id: str,
    wings: list[dict[str, Any]],
    building_graph: dict[str, Any],
    edits: list[dict[str, Any]],
    *,
    shape_type: str = "CUSTOM",
    site_boundary: list[list[float]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Edit wing lengths/widths/angles on an existing building."""
    return modify_building_wings(
        geometry_id=geometry_id,
        wings=wings,
        building_graph=building_graph,
        edits=edits,
        shape_type=shape_type,
        site_boundary=_resolve_site_boundary(site_boundary),
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Extraction — read fields out of a tool's data payload
# --------------------------------------------------------------------------- #
def extract_centerline_graph(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the centerline graph from a generate/modify result (or its data)."""
    data = _unwrap(payload)
    building_graph = data.get("building_graph")
    if isinstance(building_graph, dict):
        return building_graph.get("centerline_graph", building_graph)
    return None


def extract_wing_metadata(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull per-wing metadata (role, index, area, centroid) from a result."""
    data = _unwrap(payload)
    wings = data.get("wings")
    if not isinstance(wings, list):
        return []
    out: list[dict[str, Any]] = []
    for i, wing in enumerate(wings):
        if not isinstance(wing, dict):
            continue
        out.append(
            {
                "wing_index": wing.get("wing_index", i),
                "role": wing.get("role"),
                "area_sqm": wing.get("area_sqm"),
                "centroid": wing.get("centroid"),
            }
        )
    return out


def build_frontend_geometry_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """A compact, frontend-ready view of one building's geometry."""
    data = _unwrap(payload)
    return {
        "geometry_id": data.get("geometry_id"),
        "shape_type": data.get("shape_type"),
        "boundary": data.get("boundary"),
        "area_sqm": data.get("boundary_area_sqm"),
        "centroid": data.get("centroid"),
        "bounding_box": data.get("bounding_box"),
        "wings": extract_wing_metadata(data),
        "centerline_graph": extract_centerline_graph(data),
        "site_fit_summary": data.get("site_fit_summary"),
        "placement_options": data.get("option_catalog"),
    }
