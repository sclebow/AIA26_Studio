from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from shapely import affinity
from shapely.geometry import Polygon, box
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


def _build_legacy_shape(area: float, building_type: str) -> tuple[tuple[WingModel, ...], tuple[tuple[int, int], ...]]:
    templates: dict[str, list[tuple[float, float]]] = {
        "Y": [
            (-1.0, -3.0),
            (1.0, -3.0),
            (1.0, -0.8),
            (3.0, -0.8),
            (3.0, 1.0),
            (1.2, 1.0),
            (0.0, 3.0),
            (-1.2, 1.0),
            (-3.0, 1.0),
            (-3.0, -0.8),
            (-1.0, -0.8),
        ],
        "X": [
            (-3.0, -1.4),
            (-1.4, -1.4),
            (0.0, -3.0),
            (1.4, -1.4),
            (3.0, -1.4),
            (1.4, 0.0),
            (3.0, 1.4),
            (1.4, 1.4),
            (0.0, 3.0),
            (-1.4, 1.4),
            (-3.0, 1.4),
            (-1.4, 0.0),
        ],
        "O": [
            (-2.0, -1.0),
            (-1.0, -2.0),
            (1.0, -2.0),
            (2.0, -1.0),
            (2.0, 1.0),
            (1.0, 2.0),
            (-1.0, 2.0),
            (-2.0, 1.0),
        ],
    }
    if building_type not in templates:
        raise ValueError(f"unsupported building_type: {building_type}")

    polygon = Polygon(_scaled_template_polygon(area, templates[building_type]))
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
    }


def _face_geometry_from_polygon(polygon: Polygon) -> dict[str, Any]:
    _ensure_topologicpy_available()
    vertices = [Vertex.ByCoordinates(x, y, 0.0) for x, y in list(polygon.exterior.coords)[:-1]]
    face = Face.ByVertices(vertices)
    geometry = Topology.Geometry(face)
    return geometry if isinstance(geometry, dict) else {}


def _ensure_topologicpy_available() -> None:
    if _TOPOLOGICPY_IMPORT_ERROR is not None:
        raise RuntimeError("topologicpy is required for Team 04 graph-backed shapes") from _TOPOLOGICPY_IMPORT_ERROR


def _normalize_polygon(polygon: Polygon) -> Polygon:
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if not isinstance(polygon, Polygon):
        raise ValueError("shape generation produced a non-polygon footprint")
    return polygon
