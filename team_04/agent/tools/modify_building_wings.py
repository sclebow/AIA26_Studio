from __future__ import annotations

import math
from typing import Any

from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .building_shape_graph import ShapeModel, WingModel, serialize_shape_model
from .modify_building_boundary import _check_boundary_against_site


MODIFY_BUILDING_WINGS_TOOL_DEFINITION: dict[str, Any] = {
    "name": "modify_building_wings",
    "description": (
        "Modify individual wings in a graph-backed building by index, including wing thickness changes "
        "and wing rotation about the connected joint."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "geometry_id": {"type": "string"},
            "shape_type": {
                "type": "string",
                "description": "Original building family label. Preserved for reporting. Default: CUSTOM.",
                "default": "CUSTOM",
            },
            "wings": {
                "type": "array",
                "description": "Wing payloads returned by generate_building_boundary.",
                "items": {"type": "object"},
            },
            "building_graph": {
                "type": "object",
                "description": "Building graph payload returned by generate_building_boundary.",
            },
            "edits": {
                "type": "array",
                "description": "Wing edit operations. Each item must include wing_index and may include thickness_scale and rotation_degrees.",
                "items": {
                    "type": "object",
                    "properties": {
                        "wing_index": {"type": "integer"},
                        "thickness_scale": {"type": "number", "default": 1.0},
                        "rotation_degrees": {"type": "number", "default": 0.0},
                    },
                    "required": ["wing_index"],
                },
            },
            "site_boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "description": "Optional site boundary used to verify the modified building remains inside the site.",
            },
            "clearance": {
                "type": "number",
                "default": 0.0,
                "description": "Optional site-fit clearance margin.",
            },
        },
        "required": ["geometry_id", "wings", "building_graph", "edits"],
    },
}


def modify_building_wings(
    geometry_id: str,
    wings: list[dict[str, Any]],
    building_graph: dict[str, Any],
    edits: list[dict[str, Any]],
    shape_type: str = "CUSTOM",
    site_boundary: list[list[float]] | list[tuple[float, float, float]] | None = None,
    clearance: float = 0.0,
) -> dict[str, Any]:
    if not wings:
        raise ValueError("wings must not be empty")
    if not edits:
        raise ValueError("edits must not be empty")
    if clearance < 0:
        raise ValueError("clearance cannot be negative")

    edge_pairs = _edge_pairs_from_graph(building_graph)
    model = _shape_model_from_payload(shape_type, wings, edge_pairs)
    centerline_lookup = _centerline_lookup(building_graph)

    wings_by_index = {wing.index: wing for wing in model.wings}
    normalized_edits: list[dict[str, Any]] = []
    for raw_edit in edits:
        wing_index = int(raw_edit["wing_index"])
        existing = wings_by_index.get(wing_index)
        if existing is None:
            raise ValueError(f"unknown wing_index: {wing_index}")

        thickness_scale = float(raw_edit.get("thickness_scale", 1.0))
        rotation_degrees = float(raw_edit.get("rotation_degrees", 0.0))
        if thickness_scale <= 0:
            raise ValueError("thickness_scale must be greater than zero")

        pivot = _rotation_pivot(centerline_lookup.get(wing_index))
        updated_polygon = existing.polygon
        if not math.isclose(thickness_scale, 1.0, abs_tol=1e-9):
            updated_polygon = _scale_polygon_thickness(updated_polygon, centerline_lookup.get(wing_index), thickness_scale)
        if not math.isclose(rotation_degrees, 0.0, abs_tol=1e-9):
            updated_polygon = affinity.rotate(updated_polygon, rotation_degrees, origin=pivot, use_radians=False)

        nominal_width, nominal_length = _nominal_dimensions(updated_polygon)
        wings_by_index[wing_index] = WingModel(
            index=existing.index,
            role=existing.role,
            polygon=updated_polygon,
            nominal_width=nominal_width,
            nominal_length=nominal_length,
            editable_parameters=existing.editable_parameters,
        )
        normalized_edits.append(
            {
                "wing_index": wing_index,
                "thickness_scale": round(thickness_scale, 6),
                "rotation_degrees": round(rotation_degrees, 6),
                "rotation_pivot": [round(float(pivot[0]), 6), round(float(pivot[1]), 6), 0.0],
            }
        )

    ordered_wings = tuple(wings_by_index[index] for index in sorted(wings_by_index))
    polygon = unary_union([wing.polygon for wing in ordered_wings])
    if not isinstance(polygon, Polygon):
        polygon = polygon.buffer(0)
    if not isinstance(polygon, Polygon):
        raise ValueError("wing edits produced a non-polygon footprint")

    modified_model = ShapeModel(
        shape_type=shape_type,
        polygon=polygon,
        wings=ordered_wings,
        edge_pairs=edge_pairs,
    )
    payload = serialize_shape_model(modified_model)
    fit_summary = _check_boundary_against_site(
        [tuple(point) for point in payload["boundary"]],
        site_boundary,
        clearance,
    )

    return {
        "success": True,
        "data": {
            "geometry_id": geometry_id,
            "shape_type": shape_type,
            "applied_edits": normalized_edits,
            **payload,
            **fit_summary,
        },
        "metadata": {
            "tool_name": MODIFY_BUILDING_WINGS_TOOL_DEFINITION["name"],
            "source": "python_mock",
        },
    }


def _shape_model_from_payload(
    shape_type: str,
    wings: list[dict[str, Any]],
    edge_pairs: tuple[tuple[int, int], ...],
) -> ShapeModel:
    models: list[WingModel] = []
    for wing in wings:
        polygon = Polygon([(float(x), float(y)) for x, y, _ in wing["boundary"]])
        nominal_width = float(wing.get("nominal_width_m") or 0.0)
        nominal_length = float(wing.get("nominal_length_m") or 0.0)
        if nominal_width <= 0.0 or nominal_length <= 0.0:
            nominal_width, nominal_length = _nominal_dimensions(polygon)
        models.append(
            WingModel(
                index=int(wing["wing_index"]),
                role=str(wing.get("role", "wing")),
                polygon=polygon,
                nominal_width=nominal_width,
                nominal_length=nominal_length,
                editable_parameters=tuple(wing.get("editable_parameters", ("width", "length", "edge_rotation", "extension"))),
            )
        )

    polygon = unary_union([wing.polygon for wing in models])
    if not isinstance(polygon, Polygon):
        polygon = polygon.buffer(0)
    if not isinstance(polygon, Polygon):
        raise ValueError("input wings produced a non-polygon footprint")

    return ShapeModel(
        shape_type=shape_type,
        polygon=polygon,
        wings=tuple(sorted(models, key=lambda wing: wing.index)),
        edge_pairs=edge_pairs,
    )


def _edge_pairs_from_graph(building_graph: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    edge_pairs: list[tuple[int, int]] = []
    for edge in building_graph.get("edges", []):
        source_index = int(edge["from_wing_index"])
        target_index = int(edge["to_wing_index"])
        edge_pairs.append((source_index, target_index))
    return tuple(edge_pairs)


def _centerline_lookup(building_graph: dict[str, Any]) -> dict[int, dict[str, Any]]:
    centerline_graph = building_graph.get("centerline_graph", {})
    nodes = centerline_graph.get("nodes", [])
    adjacency_list = centerline_graph.get("adjacency_list", [])

    def node_degree(node_index: int) -> int:
        if 0 <= node_index < len(adjacency_list) and isinstance(adjacency_list[node_index], list):
            return len(adjacency_list[node_index])
        return 0

    return {
        int(edge["wing_index"]): {
            "edge": edge,
            "from_node": nodes[int(edge["from_node_index"])],
            "to_node": nodes[int(edge["to_node_index"])],
            "from_node_degree": node_degree(int(edge["from_node_index"])),
            "to_node_degree": node_degree(int(edge["to_node_index"])),
        }
        for edge in centerline_graph.get("edges", [])
    }


def _rotation_pivot(centerline_record: dict[str, Any] | None) -> tuple[float, float]:
    if centerline_record is None:
        return (0.0, 0.0)

    from_node = centerline_record["from_node"]
    to_node = centerline_record["to_node"]
    from_degree = int(centerline_record.get("from_node_degree", 0))
    to_degree = int(centerline_record.get("to_node_degree", 0))

    if from_degree > to_degree:
        point = from_node["point"]
        return (float(point[0]), float(point[1]))
    if to_degree > from_degree:
        point = to_node["point"]
        return (float(point[0]), float(point[1]))

    if from_node.get("kind") == "joint" and to_node.get("kind") != "joint":
        point = from_node["point"]
        return (float(point[0]), float(point[1]))
    if to_node.get("kind") == "joint" and from_node.get("kind") != "joint":
        point = to_node["point"]
        return (float(point[0]), float(point[1]))

    centerline = centerline_record["edge"].get("centerline", [])
    if len(centerline) == 2:
        start, end = centerline
        return ((float(start[0]) + float(end[0])) / 2.0, (float(start[1]) + float(end[1])) / 2.0)
    point = from_node["point"]
    return (float(point[0]), float(point[1]))


def _scale_polygon_thickness(polygon: Polygon, centerline_record: dict[str, Any] | None, thickness_scale: float) -> Polygon:
    if centerline_record is None:
        return polygon

    centerline = centerline_record["edge"].get("centerline", [])
    if len(centerline) != 2:
        return polygon

    start, end = centerline
    origin = ((float(start[0]) + float(end[0])) / 2.0, (float(start[1]) + float(end[1])) / 2.0)
    angle_degrees = math.degrees(math.atan2(float(end[1]) - float(start[1]), float(end[0]) - float(start[0])))
    aligned = affinity.rotate(polygon, -angle_degrees, origin=origin, use_radians=False)
    aligned = affinity.scale(aligned, xfact=1.0, yfact=thickness_scale, origin=origin)
    return affinity.rotate(aligned, angle_degrees, origin=origin, use_radians=False)


def _nominal_dimensions(polygon: Polygon) -> tuple[float, float]:
    rectangle = polygon.minimum_rotated_rectangle
    corners = list(rectangle.exterior.coords)[:-1]
    edge_lengths = [math.dist(corners[index], corners[(index + 1) % 4]) for index in range(4)]
    ordered = sorted(edge_lengths)
    return (float(ordered[0]), float(ordered[-1]))