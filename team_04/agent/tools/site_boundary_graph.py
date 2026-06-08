from __future__ import annotations

import math
from typing import Any

from .multi_building_mock import _normalize_polygon


ANALYZE_SITE_BOUNDARY_TOOL_DEFINITION: dict[str, Any] = {
    "name": "analyze_site_boundary",
    "description": "Break a site boundary into labeled corner nodes and side edges so later tools can address boundary parts explicitly.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "description": "Closed site boundary as [x, y, z] coordinates.",
            },
        },
        "required": ["site_boundary"],
    },
}


def analyze_site_boundary(
    site_boundary: list[list[float]] | list[tuple[float, float, float]],
) -> dict[str, Any]:
    graph = build_site_boundary_graph(site_boundary)
    return {
        "success": True,
        "data": {
            "site_boundary_graph": graph,
            "object_hierarchy": _build_site_hierarchy(graph),
        },
        "metadata": {
            "tool_name": ANALYZE_SITE_BOUNDARY_TOOL_DEFINITION["name"],
            "source": "python",
        },
    }


def build_site_boundary_graph(
    site_boundary: list[list[float]] | list[tuple[float, float, float]],
) -> dict[str, Any]:
    polygon = _normalize_polygon(site_boundary)
    unique_points = polygon[:-1]
    if len(unique_points) < 3:
        raise ValueError("site_boundary must define at least three corners")

    xs = [point[0] for point in unique_points]
    ys = [point[1] for point in unique_points]
    bbox_min = (min(xs), min(ys))
    bbox_max = (max(xs), max(ys))

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    adjacency_list: list[list[int]] = [[] for _ in unique_points]
    perimeter = 0.0

    for index, point in enumerate(unique_points):
        nodes.append(
            {
                "node_index": index,
                "label": f"corner_{index}",
                "point": [round(float(point[0]), 6), round(float(point[1]), 6), round(float(point[2]), 6)],
                "cardinal_hint": _corner_cardinal_hint((point[0], point[1]), bbox_min, bbox_max),
            }
        )

    point_count = len(unique_points)
    for index, start in enumerate(unique_points):
        end_index = (index + 1) % point_count
        end = unique_points[end_index]
        length = math.dist((start[0], start[1]), (end[0], end[1]))
        perimeter += length
        adjacency_list[index].append(end_index)
        adjacency_list[end_index].append(index)
        midpoint = ((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5)
        edges.append(
            {
                "edge_index": index,
                "label": f"side_{index}",
                "from_node_index": index,
                "to_node_index": end_index,
                "length_m": round(length, 6),
                "midpoint": [round(midpoint[0], 6), round(midpoint[1], 6), 0.0],
                "cardinal_hint": _edge_cardinal_hint((start[0], start[1]), (end[0], end[1]), midpoint, bbox_min, bbox_max),
            }
        )

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "perimeter_m": round(perimeter, 6),
        "nodes": nodes,
        "edges": edges,
        "adjacency_list": adjacency_list,
    }


def resolve_site_edge(
    site_boundary_graph: dict[str, Any],
    site_edge_index: int | None = None,
    site_edge_label: str | None = None,
) -> dict[str, Any] | None:
    edges = site_boundary_graph.get("edges", []) if isinstance(site_boundary_graph, dict) else []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if site_edge_index is not None and edge.get("edge_index") == site_edge_index:
            return edge
        if site_edge_label is not None and str(edge.get("label", "")).strip().lower() == site_edge_label.strip().lower():
            return edge
    return None


def edge_segment_from_graph(
    site_boundary_graph: dict[str, Any],
    edge: dict[str, Any],
) -> tuple[tuple[float, float], tuple[float, float]]:
    nodes = site_boundary_graph.get("nodes", [])
    start = nodes[edge["from_node_index"]]["point"]
    end = nodes[edge["to_node_index"]]["point"]
    return (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))


def _build_site_hierarchy(site_boundary_graph: dict[str, Any]) -> dict[str, Any]:
    nodes = site_boundary_graph.get("nodes", [])
    edges = site_boundary_graph.get("edges", [])
    return {
        "node_id": "site_boundary",
        "node_type": "site_boundary",
        "label": "Site boundary",
        "children": [
            {
                "node_id": "site_boundary:corners",
                "node_type": "corner_collection",
                "label": "Corners",
                "children": [
                    {
                        "node_id": f"site_boundary:corner:{item.get('node_index')}",
                        "node_type": "corner",
                        "label": str(item.get("label", f"corner_{index}")),
                        "cardinal_hint": item.get("cardinal_hint"),
                    }
                    for index, item in enumerate(nodes)
                    if isinstance(item, dict)
                ],
            },
            {
                "node_id": "site_boundary:sides",
                "node_type": "side_collection",
                "label": "Sides",
                "children": [
                    {
                        "node_id": f"site_boundary:side:{item.get('edge_index')}",
                        "node_type": "side",
                        "label": str(item.get("label", f"side_{index}")),
                        "cardinal_hint": item.get("cardinal_hint"),
                    }
                    for index, item in enumerate(edges)
                    if isinstance(item, dict)
                ],
            },
        ],
    }


def _corner_cardinal_hint(
    point: tuple[float, float],
    bbox_min: tuple[float, float],
    bbox_max: tuple[float, float],
) -> str:
    tolerance_x = max((bbox_max[0] - bbox_min[0]) * 0.1, 1e-6)
    tolerance_y = max((bbox_max[1] - bbox_min[1]) * 0.1, 1e-6)
    horizontal = "west" if abs(point[0] - bbox_min[0]) <= tolerance_x else "east" if abs(point[0] - bbox_max[0]) <= tolerance_x else "mid"
    vertical = "south" if abs(point[1] - bbox_min[1]) <= tolerance_y else "north" if abs(point[1] - bbox_max[1]) <= tolerance_y else "mid"
    return f"{vertical}_{horizontal}"


def _edge_cardinal_hint(
    start: tuple[float, float],
    end: tuple[float, float],
    midpoint: tuple[float, float],
    bbox_min: tuple[float, float],
    bbox_max: tuple[float, float],
) -> str:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if abs(dx) >= abs(dy):
        tolerance_y = max((bbox_max[1] - bbox_min[1]) * 0.1, 1e-6)
        if abs(midpoint[1] - bbox_min[1]) <= tolerance_y:
            return "south"
        if abs(midpoint[1] - bbox_max[1]) <= tolerance_y:
            return "north"
    else:
        tolerance_x = max((bbox_max[0] - bbox_min[0]) * 0.1, 1e-6)
        if abs(midpoint[0] - bbox_min[0]) <= tolerance_x:
            return "west"
        if abs(midpoint[0] - bbox_max[0]) <= tolerance_x:
            return "east"
    return "side"