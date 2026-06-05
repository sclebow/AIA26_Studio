from __future__ import annotations

from typing import Any

from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

from .multi_building_mock import _normalize_polygon
from .site_boundary_graph import build_site_boundary_graph, edge_segment_from_graph, resolve_site_edge


MEASURE_BOUNDARY_PROXIMITY_TOOL_DEFINITION: dict[str, Any] = {
    "name": "measure_boundary_proximity",
    "description": "Measure how close a building boundary is to each labeled site side and corner.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "geometry_id": {"type": "string"},
            "building_boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "description": "Closed building footprint boundary as [x, y, z] coordinates.",
            },
            "site_boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "description": "Closed site boundary as [x, y, z] coordinates.",
            },
            "site_edge_index": {
                "type": "integer",
                "description": "Optional site edge index to highlight in the result.",
            },
            "site_edge_label": {
                "type": "string",
                "description": "Optional site edge label such as side_0 to highlight in the result.",
            },
        },
        "required": ["building_boundary", "site_boundary"],
    },
}


def measure_boundary_proximity(
    building_boundary: list[list[float]] | list[tuple[float, float, float]],
    site_boundary: list[list[float]] | list[tuple[float, float, float]],
    geometry_id: str = "",
    site_edge_index: int | None = None,
    site_edge_label: str | None = None,
) -> dict[str, Any]:
    data = measure_boundary_proximity_data(
        building_boundary=building_boundary,
        site_boundary=site_boundary,
        site_edge_index=site_edge_index,
        site_edge_label=site_edge_label,
    )
    if geometry_id:
        data["geometry_id"] = geometry_id
    return {
        "success": True,
        "data": data,
        "metadata": {
            "tool_name": MEASURE_BOUNDARY_PROXIMITY_TOOL_DEFINITION["name"],
            "source": "python",
        },
    }


def measure_boundary_proximity_data(
    *,
    building_boundary: list[list[float]] | list[tuple[float, float, float]],
    site_boundary: list[list[float]] | list[tuple[float, float, float]],
    site_edge_index: int | None = None,
    site_edge_label: str | None = None,
) -> dict[str, Any]:
    normalized_building = _normalize_polygon(building_boundary)
    building_line = LineString([(float(point[0]), float(point[1])) for point in normalized_building])
    site_graph = build_site_boundary_graph(site_boundary)

    edge_proximities: list[dict[str, Any]] = []
    for edge in site_graph["edges"]:
        start, end = edge_segment_from_graph(site_graph, edge)
        edge_line = LineString([start, end])
        building_point, site_point = nearest_points(building_line, edge_line)
        edge_proximities.append(
            {
                "edge_index": edge["edge_index"],
                "label": edge["label"],
                "cardinal_hint": edge.get("cardinal_hint"),
                "minimum_distance_m": round(float(building_point.distance(site_point)), 6),
                "nearest_building_point": [round(building_point.x, 6), round(building_point.y, 6), 0.0],
                "nearest_site_point": [round(site_point.x, 6), round(site_point.y, 6), 0.0],
            }
        )

    corner_proximities: list[dict[str, Any]] = []
    for node in site_graph["nodes"]:
        site_corner = Point(float(node["point"][0]), float(node["point"][1]))
        building_point, corner_point = nearest_points(building_line, site_corner)
        corner_proximities.append(
            {
                "node_index": node["node_index"],
                "label": node["label"],
                "cardinal_hint": node.get("cardinal_hint"),
                "minimum_distance_m": round(float(building_point.distance(corner_point)), 6),
                "nearest_building_point": [round(building_point.x, 6), round(building_point.y, 6), 0.0],
                "site_corner_point": [round(corner_point.x, 6), round(corner_point.y, 6), 0.0],
            }
        )

    edge_proximities.sort(key=lambda item: (item["minimum_distance_m"], item["edge_index"]))
    corner_proximities.sort(key=lambda item: (item["minimum_distance_m"], item["node_index"]))
    selected_edge = resolve_site_edge(site_graph, site_edge_index=site_edge_index, site_edge_label=site_edge_label)
    highlighted_edge = None
    if selected_edge is not None:
        highlighted_edge = next(
            (item for item in edge_proximities if item["edge_index"] == selected_edge["edge_index"]),
            None,
        )

    return {
        "site_boundary_graph": site_graph,
        "minimum_distance_m": edge_proximities[0]["minimum_distance_m"] if edge_proximities else None,
        "nearest_site_edge": edge_proximities[0] if edge_proximities else None,
        "nearest_site_corner": corner_proximities[0] if corner_proximities else None,
        "selected_site_edge": highlighted_edge,
        "edge_proximities": edge_proximities,
        "corner_proximities": corner_proximities,
    }