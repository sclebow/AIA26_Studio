from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from shapely import affinity
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

_TOPOLOGICPY_IMPORT_ERROR: Exception | None = None

try:
    from topologicpy.Edge import Edge
    from topologicpy.Face import Face
    from topologicpy.Graph import Graph
    from topologicpy.Topology import Topology
    from topologicpy.Vertex import Vertex
except Exception as exc:  # pragma: no cover - exercised through tool calls
    Edge = None
    Face = None
    Graph = None
    Topology = None
    Vertex = None
    _TOPOLOGICPY_IMPORT_ERROR = exc


EDITABLE_PARAMETERS = ("width", "length", "edge_rotation", "extension")
SUPPORTED_WINGED_BUILDING_TYPES = ("I", "L", "T", "U", "H")


@dataclass(frozen=True)
class WingModel:
    index: int
    role: str
    polygon: Polygon
    nominal_width: float
    nominal_length: float
    editable_parameters: tuple[str, ...] = EDITABLE_PARAMETERS


@dataclass(frozen=True)
class ShapeModel:
    shape_type: str
    polygon: Polygon
    wings: tuple[WingModel, ...]
    edge_pairs: tuple[tuple[int, int], ...]


def build_shape_model(
    *,
    area: float,
    building_type: str,
    building_depth: float,
    shape_ratio: float,
) -> ShapeModel:
    normalized_type = building_type.upper()
    if normalized_type in SUPPORTED_WINGED_BUILDING_TYPES:
        wings, edge_pairs = _build_winged_shape(
            area=area,
            building_type=normalized_type,
            building_depth=building_depth,
            shape_ratio=shape_ratio,
        )
    else:
        wings, edge_pairs = _build_legacy_shape(area=area, building_type=normalized_type)

    polygon = _normalize_polygon(unary_union([wing.polygon for wing in wings]))
    centroid = polygon.centroid
    centered_polygon = affinity.translate(polygon, xoff=-centroid.x, yoff=-centroid.y)
    centered_wings = tuple(
        WingModel(
            index=wing.index,
            role=wing.role,
            polygon=affinity.translate(wing.polygon, xoff=-centroid.x, yoff=-centroid.y),
            nominal_width=wing.nominal_width,
            nominal_length=wing.nominal_length,
            editable_parameters=wing.editable_parameters,
        )
        for wing in wings
    )
    return ShapeModel(
        shape_type=normalized_type,
        polygon=centered_polygon,
        wings=centered_wings,
        edge_pairs=edge_pairs,
    )


def apply_shape_transform(
    model: ShapeModel,
    *,
    translation_xy: tuple[float, float] = (0.0, 0.0),
    rotation_degrees: float = 0.0,
    is_mirrored: bool = False,
    mirror_axis: str = "y",
) -> ShapeModel:
    polygon = model.polygon
    wings = list(model.wings)

    if is_mirrored:
        scale_x = -1.0 if mirror_axis == "y" else 1.0
        scale_y = -1.0 if mirror_axis == "x" else 1.0
        polygon = affinity.scale(polygon, xfact=scale_x, yfact=scale_y, origin=(0.0, 0.0))
        wings = [
            WingModel(
                index=wing.index,
                role=wing.role,
                polygon=affinity.scale(wing.polygon, xfact=scale_x, yfact=scale_y, origin=(0.0, 0.0)),
                nominal_width=wing.nominal_width,
                nominal_length=wing.nominal_length,
                editable_parameters=wing.editable_parameters,
            )
            for wing in wings
        ]

    if not math.isclose(rotation_degrees, 0.0, abs_tol=1e-9):
        polygon = affinity.rotate(polygon, rotation_degrees, origin=(0.0, 0.0), use_radians=False)
        wings = [
            WingModel(
                index=wing.index,
                role=wing.role,
                polygon=affinity.rotate(wing.polygon, rotation_degrees, origin=(0.0, 0.0), use_radians=False),
                nominal_width=wing.nominal_width,
                nominal_length=wing.nominal_length,
                editable_parameters=wing.editable_parameters,
            )
            for wing in wings
        ]

    xoff, yoff = float(translation_xy[0]), float(translation_xy[1])
    if not math.isclose(xoff, 0.0, abs_tol=1e-9) or not math.isclose(yoff, 0.0, abs_tol=1e-9):
        polygon = affinity.translate(polygon, xoff=xoff, yoff=yoff)
        wings = [
            WingModel(
                index=wing.index,
                role=wing.role,
                polygon=affinity.translate(wing.polygon, xoff=xoff, yoff=yoff),
                nominal_width=wing.nominal_width,
                nominal_length=wing.nominal_length,
                editable_parameters=wing.editable_parameters,
            )
            for wing in wings
        ]

    return ShapeModel(
        shape_type=model.shape_type,
        polygon=polygon,
        wings=tuple(wings),
        edge_pairs=model.edge_pairs,
    )


def shape_model_boundary_points(model: ShapeModel) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in model.polygon.exterior.coords]


def serialize_shape_model(model: ShapeModel) -> dict[str, Any]:
    graph_payload = _build_graph_payload(model.wings, model.edge_pairs)
    wing_payloads = [_serialize_wing(wing) for wing in model.wings]
    bounds = model.polygon.bounds
    centroid = model.polygon.centroid

    return {
        "boundary": _serialize_polygon(model.polygon),
        "boundary_area_sqm": round(model.polygon.area, 6),
        "perimeter_m": round(model.polygon.length, 6),
        "centroid": [round(centroid.x, 6), round(centroid.y, 6), 0.0],
        "bounding_box": {
            "min": [round(bounds[0], 6), round(bounds[1], 6), 0.0],
            "max": [round(bounds[2], 6), round(bounds[3], 6), 0.0],
        },
        "wings": wing_payloads,
        "building_graph": graph_payload,
        "topologic_shape": {
            "backend": "topologicpy",
            "face_geometry": _face_geometry_from_polygon(model.polygon),
            "wing_face_geometries": [_face_geometry_from_polygon(wing.polygon) for wing in model.wings],
        },
    }


def _build_winged_shape(
    *,
    area: float,
    building_type: str,
    building_depth: float,
    shape_ratio: float,
) -> tuple[tuple[WingModel, ...], tuple[tuple[int, int], ...]]:
    if building_type == "I":
        width = _effective_width(area, building_depth, minimum_units=1.0)
        length = area / width
        return (
            (
                WingModel(
                    index=0,
                    role="main_bar",
                    polygon=box(0.0, 0.0, length, width),
                    nominal_width=width,
                    nominal_length=length,
                ),
            ),
            (),
        )

    if building_type == "L":
        width = _effective_width(area, building_depth, minimum_units=1.0)
        extra = max(area / width - width, 0.0)
        vertical_length = width + extra * shape_ratio
        horizontal_length = width + extra * (1.0 - shape_ratio)
        return (
            (
                WingModel(0, "vertical_wing", box(0.0, 0.0, width, vertical_length), width, vertical_length),
                WingModel(1, "horizontal_wing", box(0.0, 0.0, horizontal_length, width), width, horizontal_length),
            ),
            ((0, 1),),
        )

    if building_type == "T":
        width = _effective_width(area, building_depth, minimum_units=1.0)
        extra = max(area / width - width, 0.0)
        stem_length = width + extra * shape_ratio
        cap_width = width + extra * (1.0 - shape_ratio)
        cap_x0 = -(cap_width - width) / 2.0
        return (
            (
                WingModel(0, "stem", box(0.0, 0.0, width, stem_length), width, stem_length),
                WingModel(1, "crossbar", box(cap_x0, stem_length - width, cap_x0 + cap_width, stem_length), width, cap_width),
            ),
            ((0, 1),),
        )

    if building_type == "U":
        width = _effective_width(area, building_depth, minimum_units=2.0)
        extra_total = max(area / width - (2.0 * width), 0.0)
        leg_extra = extra_total * shape_ratio
        bottom_extra = extra_total - leg_extra
        leg_height = width + (leg_extra / 2.0)
        bottom_width = (2.0 * width) + bottom_extra
        return (
            (
                WingModel(0, "base", box(0.0, 0.0, bottom_width, width), width, bottom_width),
                WingModel(1, "left_wing", box(0.0, 0.0, width, leg_height), width, leg_height),
                WingModel(2, "right_wing", box(bottom_width - width, 0.0, bottom_width, leg_height), width, leg_height),
            ),
            ((0, 1), (0, 2)),
        )

    width = _effective_width(area, building_depth, minimum_units=2.0)
    extra_total = max(area / width - (2.0 * width), 0.0)
    bar_extra = extra_total * shape_ratio
    connector_width = extra_total - bar_extra
    bar_height = width + (bar_extra / 2.0)
    connector_y0 = (bar_height - width) / 2.0
    return (
        (
            WingModel(0, "left_wing", box(0.0, 0.0, width, bar_height), width, bar_height),
            WingModel(1, "connector", box(width, connector_y0, width + connector_width, connector_y0 + width), width, connector_width),
            WingModel(2, "right_wing", box(width + connector_width, 0.0, (2.0 * width) + connector_width, bar_height), width, bar_height),
        ),
        ((0, 1), (1, 2)),
    )


#: Octagonal 'O' (ring-ish) footprint template, scaled to area at build time.
_O_TEMPLATE: list[tuple[float, float]] = [
    (-2.0, -1.0),
    (-1.0, -2.0),
    (1.0, -2.0),
    (2.0, -1.0),
    (2.0, 1.0),
    (1.0, 2.0),
    (-1.0, 2.0),
    (-2.0, 1.0),
]


def _largest_polygon(geom: Any) -> Polygon:
    if isinstance(geom, Polygon):
        return geom
    return max(geom.geoms, key=lambda part: part.area)


def _letter_y_polygon(arm_width: float = 1.3, spread: float = 2.0, arm_len: float = 3.0, stem_len: float = 3.0) -> Polygon:
    """A clean letter-Y footprint: a vertical stem that splits into two diagonal
    arms forming a V, all of uniform width (union of three flat-ended bars)."""
    half = arm_width / 2.0
    stem = LineString([(0.0, -stem_len), (0.0, 0.0)]).buffer(half, cap_style=2, join_style=2)
    left = LineString([(0.0, 0.0), (-spread, arm_len)]).buffer(half, cap_style=2, join_style=2)
    right = LineString([(0.0, 0.0), (spread, arm_len)]).buffer(half, cap_style=2, join_style=2)
    return _largest_polygon(unary_union([stem, left, right]))


def _letter_x_polygon(arm_width: float = 1.3, reach: float = 2.6) -> Polygon:
    """A clean letter-X footprint: two uniform-width diagonal bars crossing at the
    centre (union of two flat-ended bars)."""
    half = arm_width / 2.0
    bar1 = LineString([(-reach, -reach), (reach, reach)]).buffer(half, cap_style=2, join_style=2)
    bar2 = LineString([(-reach, reach), (reach, -reach)]).buffer(half, cap_style=2, join_style=2)
    return _largest_polygon(unary_union([bar1, bar2]))


def _scale_polygon_to_area(polygon: Polygon, area: float) -> Polygon:
    scale = math.sqrt(area / polygon.area)
    return affinity.scale(polygon, xfact=scale, yfact=scale, origin=(0.0, 0.0))


def _build_legacy_shape(area: float, building_type: str) -> tuple[tuple[WingModel, ...], tuple[tuple[int, int], ...]]:
    if building_type == "Y":
        polygon = _scale_polygon_to_area(_letter_y_polygon(), area)
    elif building_type == "X":
        polygon = _scale_polygon_to_area(_letter_x_polygon(), area)
    elif building_type == "O":
        polygon = Polygon(_scaled_template_polygon(area, _O_TEMPLATE))
    else:
        raise ValueError(f"unsupported building_type: {building_type}")

    nominal_span = math.sqrt(area)
    return (
        (
            WingModel(
                index=0,
                role="main_mass",
                polygon=polygon,
                nominal_width=nominal_span,
                nominal_length=nominal_span,
            ),
        ),
        (),
    )


def _effective_width(area: float, requested_depth: float, minimum_units: float) -> float:
    max_depth = math.sqrt(area / minimum_units) * 0.9
    width = min(requested_depth, max_depth)
    if width <= 0:
        raise ValueError("area and building_depth produce an invalid footprint")
    return width


def _scaled_template_polygon(area: float, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    template = Polygon(points)
    scale = math.sqrt(area / template.area)
    return [(x * scale, y * scale) for x, y in points]


def _serialize_wing(wing: WingModel) -> dict[str, Any]:
    centroid = wing.polygon.centroid
    return {
        "wing_index": wing.index,
        "role": wing.role,
        "area_sqm": round(wing.polygon.area, 6),
        "centroid": [round(centroid.x, 6), round(centroid.y, 6), 0.0],
        "boundary": _serialize_polygon(wing.polygon),
        "nominal_width_m": round(wing.nominal_width, 6),
        "nominal_length_m": round(wing.nominal_length, 6),
        "editable_parameters": list(wing.editable_parameters),
    }


def _serialize_polygon(polygon: Polygon) -> list[list[float]]:
    return [[round(float(x), 6), round(float(y), 6), 0.0] for x, y in polygon.exterior.coords]


def _build_graph_payload(wings: tuple[WingModel, ...], edge_pairs: tuple[tuple[int, int], ...]) -> dict[str, Any]:
    _ensure_topologicpy_available()
    if not wings:
        return {
            "backend": "topologicpy",
            "node_count": 0,
            "edge_count": 0,
            "edges": [],
            "adjacency_list": [],
            "centerline_graph": {
                "node_count": 0,
                "edge_count": 0,
                "nodes": [],
                "edges": [],
                "adjacency_list": [],
            },
        }

    adjacency_list = [[] for _ in wings]
    for source_index, target_index in edge_pairs:
        adjacency_list[source_index].append(target_index)
        adjacency_list[target_index].append(source_index)
    adjacency_list = [sorted(neighbors) for neighbors in adjacency_list]

    if len(wings) > 1:
        vertices = [Vertex.ByCoordinates(wing.polygon.centroid.x, wing.polygon.centroid.y, 0.0) for wing in wings]
        edges = []
        for source_index, target_index in edge_pairs:
            edge = Edge.ByVertices(vertices[source_index], vertices[target_index])
            if edge is not None:
                edges.append(edge)
        Graph.ByVerticesEdges(vertices, edges)

    centerline_graph = _build_centerline_graph(wings, edge_pairs)

    return {
        "backend": "topologicpy",
        "node_count": len(wings),
        "edge_count": len(edge_pairs),
        "edges": [
            {
                "from_wing_index": source_index,
                "to_wing_index": target_index,
                "relationship": "connected",
            }
            for source_index, target_index in edge_pairs
        ],
        "adjacency_list": adjacency_list,
        "centerline_graph": centerline_graph,
    }


def _build_centerline_graph(
    wings: tuple[WingModel, ...],
    edge_pairs: tuple[tuple[int, int], ...],
) -> dict[str, Any]:
    centerlines = {wing.index: _wing_centerline_segment(wing) for wing in wings}
    wing_adjacency = {wing.index: [] for wing in wings}
    for source_index, target_index in edge_pairs:
        point = _segment_intersection_point(centerlines[source_index], centerlines[target_index])
        if point is None:
            point = _fallback_joint_point(centerlines[source_index], centerlines[target_index])
        wing_adjacency[source_index].append(point)
        wing_adjacency[target_index].append(point)

    node_records: list[dict[str, Any]] = []
    node_lookup: dict[tuple[int, int, int], int] = {}

    def register_node(point: tuple[float, float, float], kind: str, wing_index: int) -> int:
        key = (round(point[0] * 1_000_000), round(point[1] * 1_000_000), round(point[2] * 1_000_000))
        existing_index = node_lookup.get(key)
        if existing_index is not None:
            record = node_records[existing_index]
            connected = set(record["connected_wings"])
            connected.add(wing_index)
            record["connected_wings"] = sorted(connected)
            if kind == "joint":
                record["kind"] = "joint"
            return existing_index

        node_index = len(node_records)
        node_lookup[key] = node_index
        node_records.append(
            {
                "node_index": node_index,
                "kind": kind,
                "point": [round(point[0], 6), round(point[1], 6), round(point[2], 6)],
                "connected_wings": [wing_index],
            }
        )
        return node_index

    centerline_edges: list[dict[str, Any]] = []
    for wing in wings:
        segment_start, segment_end = centerlines[wing.index]
        joint_points = wing_adjacency[wing.index]
        if not joint_points:
            start_node_index = register_node(segment_start, "endpoint", wing.index)
            end_node_index = register_node(segment_end, "endpoint", wing.index)
            edge_start = segment_start
            edge_end = segment_end
        elif len(joint_points) == 1:
            joint_point = joint_points[0]
            joint_node_index = register_node(joint_point, "joint", wing.index)
            free_endpoint = max(
                (segment_start, segment_end),
                key=lambda point: _distance_xy(point, joint_point),
            )
            free_node_index = register_node(free_endpoint, "endpoint", wing.index)
            if _distance_xy(free_endpoint, segment_start) <= 1e-6:
                start_node_index, end_node_index = free_node_index, joint_node_index
                edge_start, edge_end = free_endpoint, joint_point
            else:
                start_node_index, end_node_index = joint_node_index, free_node_index
                edge_start, edge_end = joint_point, free_endpoint
        else:
            ordered_joint_points = sorted(
                joint_points,
                key=lambda point: _line_parameter(point, segment_start, segment_end),
            )
            start_joint = ordered_joint_points[0]
            end_joint = ordered_joint_points[-1]
            start_node_index = register_node(start_joint, "joint", wing.index)
            end_node_index = register_node(end_joint, "joint", wing.index)
            edge_start, edge_end = start_joint, end_joint

        centerline_edges.append(
            {
                "edge_index": len(centerline_edges),
                "wing_index": wing.index,
                "role": wing.role,
                "from_node_index": start_node_index,
                "to_node_index": end_node_index,
                "centerline": [
                    [round(edge_start[0], 6), round(edge_start[1], 6), round(edge_start[2], 6)],
                    [round(edge_end[0], 6), round(edge_end[1], 6), round(edge_end[2], 6)],
                ],
                "length_m": round(_distance_xy(edge_start, edge_end), 6),
                "nominal_width_m": round(wing.nominal_width, 6),
                "estimated_area_sqm": round(wing.polygon.area, 6),
            }
        )

    node_adjacency = [[] for _ in node_records]
    for edge in centerline_edges:
        source_index = edge["from_node_index"]
        target_index = edge["to_node_index"]
        node_adjacency[source_index].append(target_index)
        node_adjacency[target_index].append(source_index)
    node_adjacency = [sorted(set(neighbors)) for neighbors in node_adjacency]

    if centerline_edges:
        vertices = [Vertex.ByCoordinates(*record["point"]) for record in node_records]
        edges = []
        for edge in centerline_edges:
            topology_edge = Edge.ByVertices(vertices[edge["from_node_index"]], vertices[edge["to_node_index"]])
            if topology_edge is not None:
                edges.append(topology_edge)
        if edges:
            Graph.ByVerticesEdges(vertices, edges)

    return {
        "node_count": len(node_records),
        "edge_count": len(centerline_edges),
        "nodes": node_records,
        "edges": centerline_edges,
        "adjacency_list": node_adjacency,
    }


def _wing_centerline_segment(wing: WingModel) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    rectangle = wing.polygon.minimum_rotated_rectangle
    corners = list(rectangle.exterior.coords)[:-1]
    edge_lengths = [math.dist(corners[index], corners[(index + 1) % 4]) for index in range(4)]

    if edge_lengths[0] >= edge_lengths[1]:
        start = _midpoint_xy(corners[1], corners[2])
        end = _midpoint_xy(corners[3], corners[0])
    else:
        start = _midpoint_xy(corners[0], corners[1])
        end = _midpoint_xy(corners[2], corners[3])
    return start, end


def _segment_intersection_point(
    segment_a: tuple[tuple[float, float, float], tuple[float, float, float]],
    segment_b: tuple[tuple[float, float, float], tuple[float, float, float]],
) -> tuple[float, float, float] | None:
    line_a = LineString([(segment_a[0][0], segment_a[0][1]), (segment_a[1][0], segment_a[1][1])])
    line_b = LineString([(segment_b[0][0], segment_b[0][1]), (segment_b[1][0], segment_b[1][1])])
    intersection = line_a.intersection(line_b)
    if intersection.is_empty:
        return None
    if hasattr(intersection, "geoms"):
        intersection = intersection.centroid
    return (float(intersection.x), float(intersection.y), 0.0)


def _fallback_joint_point(
    segment_a: tuple[tuple[float, float, float], tuple[float, float, float]],
    segment_b: tuple[tuple[float, float, float], tuple[float, float, float]],
) -> tuple[float, float, float]:
    candidate_pairs = (
        (segment_a[0], segment_b[0]),
        (segment_a[0], segment_b[1]),
        (segment_a[1], segment_b[0]),
        (segment_a[1], segment_b[1]),
    )
    point_a, point_b = min(candidate_pairs, key=lambda pair: _distance_xy(pair[0], pair[1]))
    return (
        round((point_a[0] + point_b[0]) / 2.0, 6),
        round((point_a[1] + point_b[1]) / 2.0, 6),
        0.0,
    )


def _midpoint_xy(point_a: tuple[float, float], point_b: tuple[float, float]) -> tuple[float, float, float]:
    return (
        (float(point_a[0]) + float(point_b[0])) / 2.0,
        (float(point_a[1]) + float(point_b[1])) / 2.0,
        0.0,
    )


def _distance_xy(point_a: tuple[float, float, float], point_b: tuple[float, float, float]) -> float:
    return math.dist((point_a[0], point_a[1]), (point_b[0], point_b[1]))


def _line_parameter(
    point: tuple[float, float, float],
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> float:
    direction_x = end[0] - start[0]
    direction_y = end[1] - start[1]
    denominator = (direction_x * direction_x) + (direction_y * direction_y)
    if denominator <= 1e-12:
        return 0.0
    return ((point[0] - start[0]) * direction_x + (point[1] - start[1]) * direction_y) / denominator


def _face_geometry_from_polygon(polygon: Polygon) -> dict[str, Any]:
    _ensure_topologicpy_available()
    vertices = [Vertex.ByCoordinates(x, y, 0.0) for x, y in _sanitized_polygon_vertices(polygon)]
    if len(vertices) < 3:
        return {}
    face = Face.ByVertices(vertices)
    if face is None:
        return {}
    geometry = Topology.Geometry(face)
    return geometry if isinstance(geometry, dict) else {}


def _sanitized_polygon_vertices(polygon: Polygon) -> list[tuple[float, float]]:
    cleaned: list[tuple[float, float]] = []
    for x, y in list(polygon.exterior.coords):
        point = (float(x), float(y))
        if not cleaned or math.dist(cleaned[-1], point) > 1e-6:
            cleaned.append(point)

    if len(cleaned) > 1 and math.dist(cleaned[0], cleaned[-1]) <= 1e-6:
        cleaned.pop()

    return cleaned


def _ensure_topologicpy_available() -> None:
    if _TOPOLOGICPY_IMPORT_ERROR is not None:
        raise RuntimeError("topologicpy is required for Team 04 graph-backed shapes") from _TOPOLOGICPY_IMPORT_ERROR


def _normalize_polygon(polygon: Polygon) -> Polygon:
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if not isinstance(polygon, Polygon):
        raise ValueError("shape generation produced a non-polygon footprint")
    return polygon
