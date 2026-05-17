from __future__ import annotations

import math
import uuid
from typing import Any

IMPORT_BUILDING_BOUNDARY_TOOL_DEFINITION: dict[str, Any] = {
    "name": "import_building_boundary_04",
    "description": "Create Rhino/Grasshopper geometry from a Python-generated closed building boundary.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "geometry_id": {"type": "string"},
            "boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "description": "Closed building footprint polyline as [x, y, z] coordinates.",
            },
            "layer_name": {
                "type": "string",
                "default": "TerraPilot_Output::BuildingFootprint",
            },
            "closed": {"type": "boolean", "default": True},
        },
        "required": ["geometry_id", "boundary"],
    },
}

REMAINING_BUILDABLE_POSITIONS_TOOL_DEFINITION: dict[str, Any] = {
    "name": "remaining_buildable_positions_04",
    "description": "Pixelize the remaining site and return feasible centroid candidates for the next building.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "placed_buildings": {
                "type": "array",
                "description": "Placed building payloads with geometry_id and boundary.",
            },
            "candidate_building_boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "grid_size": {"type": "number", "default": 10.0},
            "clearance": {"type": "number", "default": 0.0},
            "max_positions": {"type": "integer", "default": 50},
        },
        "required": ["site_boundary", "placed_buildings"],
    },
}

REQUESTED_POSITION_CHECKER_TOOL_DEFINITION: dict[str, Any] = {
    "name": "requested_position_checker_04",
    "description": "Check whether a user-requested point can host the proposed building and suggest nearby feasible positions.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "placed_buildings": {"type": "array"},
            "proposed_boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "requested_point": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            },
            "candidate_positions": {"type": "array"},
            "clearance": {"type": "number", "default": 0.0},
            "max_suggestions": {"type": "integer", "default": 5},
        },
        "required": ["site_boundary", "placed_buildings", "proposed_boundary", "requested_point"],
    },
}


def mock_import_building_boundary(
    geometry_id: str,
    boundary: list[list[float]] | list[tuple[float, float, float]],
    layer_name: str = "TerraPilot_Output::BuildingFootprint",
    closed: bool = True,
) -> dict[str, Any]:
    normalized_boundary = _normalize_polygon(boundary)
    if closed and normalized_boundary[0] != normalized_boundary[-1]:
        normalized_boundary = normalized_boundary + [normalized_boundary[0]]

    return {
        "success": True,
        "data": {
            "geometry_id": geometry_id,
            "footprint_guid": f"mock_rhino_curve_{uuid.uuid4().hex[:12]}",
            "layer_name": layer_name,
            "is_closed": normalized_boundary[0] == normalized_boundary[-1],
            "point_count": len(normalized_boundary),
            "boundary": [[x, y, z] for x, y, z in normalized_boundary],
        },
        "metadata": {
            "tool_name": IMPORT_BUILDING_BOUNDARY_TOOL_DEFINITION["name"],
            "source": "python_mock",
        },
    }



def mock_remaining_buildable_positions(
    site_boundary: list[list[float]] | list[tuple[float, float, float]],
    placed_buildings: list[dict[str, Any]],
    candidate_building_boundary: list[list[float]] | list[tuple[float, float, float]] | None = None,
    grid_size: float = 10.0,
    clearance: float = 0.0,
    max_positions: int = 50,
) -> dict[str, Any]:
    if grid_size <= 0:
        raise ValueError("grid_size must be greater than 0")
    if max_positions <= 0:
        raise ValueError("max_positions must be greater than 0")

    site_polygon = _normalize_polygon(site_boundary)
    candidate_polygon = _normalize_polygon(candidate_building_boundary) if candidate_building_boundary else None
    occupied_polygons = [_normalize_polygon(item["boundary"]) for item in placed_buildings if isinstance(item, dict) and item.get("boundary")]

    bbox_min, bbox_max = _bounding_box(site_polygon)
    xs = _sample_axis(bbox_min[0], bbox_max[0], grid_size)
    ys = _sample_axis(bbox_min[1], bbox_max[1], grid_size)

    candidates: list[list[float]] = []
    for x in xs:
        for y in ys:
            test_point = (x, y)
            if not _point_in_polygon(test_point, site_polygon):
                continue
            if candidate_polygon is not None:
                translated = _translate_polygon_to_centroid(candidate_polygon, test_point)
                is_valid, _ = _assess_position(site_polygon, occupied_polygons, translated, clearance)
                if not is_valid:
                    continue
            else:
                if any(_point_in_polygon(test_point, polygon) for polygon in occupied_polygons):
                    continue
            candidates.append([round(x, 6), round(y, 6), 0.0])
            if len(candidates) >= max_positions:
                break
        if len(candidates) >= max_positions:
            break

    return {
        "success": True,
        "data": {
            "candidate_positions": candidates,
            "candidate_count": len(candidates),
            "grid_size": grid_size,
            "clearance": clearance,
            "site_bounding_box": {
                "min": [round(bbox_min[0], 6), round(bbox_min[1], 6), 0.0],
                "max": [round(bbox_max[0], 6), round(bbox_max[1], 6), 0.0],
            },
            "occupied_geometry_ids": [str(item.get("geometry_id", "")) for item in placed_buildings if isinstance(item, dict)],
        },
        "metadata": {
            "tool_name": REMAINING_BUILDABLE_POSITIONS_TOOL_DEFINITION["name"],
            "source": "python_mock",
        },
    }



def mock_check_requested_position(
    site_boundary: list[list[float]] | list[tuple[float, float, float]],
    placed_buildings: list[dict[str, Any]],
    proposed_boundary: list[list[float]] | list[tuple[float, float, float]],
    requested_point: list[float] | tuple[float, float],
    candidate_positions: list[list[float]] | None = None,
    clearance: float = 0.0,
    max_suggestions: int = 5,
) -> dict[str, Any]:
    if len(requested_point) != 2:
        raise ValueError("requested_point must contain exactly two numbers")
    if max_suggestions <= 0:
        raise ValueError("max_suggestions must be greater than 0")

    site_polygon = _normalize_polygon(site_boundary)
    occupied_polygons = [_normalize_polygon(item["boundary"]) for item in placed_buildings if isinstance(item, dict) and item.get("boundary")]
    proposed_polygon = _normalize_polygon(proposed_boundary)
    target_point = (float(requested_point[0]), float(requested_point[1]))
    translated_polygon = _translate_polygon_to_centroid(proposed_polygon, target_point)
    feasible, reasons = _assess_position(site_polygon, occupied_polygons, translated_polygon, clearance)

    candidate_list = candidate_positions or []
    if not candidate_list:
        candidate_result = mock_remaining_buildable_positions(
            site_boundary=site_polygon,
            placed_buildings=placed_buildings,
            candidate_building_boundary=proposed_polygon,
            grid_size=max(5.0, clearance or 10.0),
            clearance=clearance,
            max_positions=max(10, max_suggestions * 4),
        )
        candidate_list = candidate_result["data"]["candidate_positions"]

    sorted_candidates = sorted(
        candidate_list,
        key=lambda point: math.dist((float(point[0]), float(point[1])), target_point),
    )
    suggestions = sorted_candidates[:max_suggestions]

    return {
        "success": True,
        "data": {
            "requested_point": [target_point[0], target_point[1], 0.0],
            "is_feasible": feasible,
            "geometric_reasons": reasons,
            "suggested_positions": suggestions,
            "translated_boundary": [[round(x, 6), round(y, 6), round(z, 6)] for x, y, z in translated_polygon],
        },
        "metadata": {
            "tool_name": REQUESTED_POSITION_CHECKER_TOOL_DEFINITION["name"],
            "source": "python_mock",
        },
    }



def _normalize_polygon(points: list[list[float]] | list[tuple[float, float, float]] | None) -> list[tuple[float, float, float]]:
    if not points:
        raise ValueError("polygon requires at least one point")
    normalized: list[tuple[float, float, float]] = []
    for point in points:
        if len(point) < 2:
            raise ValueError("polygon points must include at least x and y")
        x = float(point[0])
        y = float(point[1])
        z = float(point[2]) if len(point) > 2 else 0.0
        normalized.append((x, y, z))
    if normalized[0] != normalized[-1]:
        normalized.append(normalized[0])
    return normalized



def _sample_axis(start: float, end: float, step: float) -> list[float]:
    values: list[float] = []
    current = start + (step / 2.0)
    while current < end:
        values.append(current)
        current += step
    return values



def _bounding_box(polygon: list[tuple[float, float, float]]) -> tuple[tuple[float, float], tuple[float, float]]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return (min(xs), min(ys)), (max(xs), max(ys))



def _polygon_centroid(polygon: list[tuple[float, float, float]]) -> tuple[float, float]:
    signed_area = 0.0
    centroid_x = 0.0
    centroid_y = 0.0
    for index in range(len(polygon) - 1):
        x1, y1, _ = polygon[index]
        x2, y2, _ = polygon[index + 1]
        cross = x1 * y2 - x2 * y1
        signed_area += cross
        centroid_x += (x1 + x2) * cross
        centroid_y += (y1 + y2) * cross
    signed_area *= 0.5
    if math.isclose(signed_area, 0.0, abs_tol=1e-9):
        raise ValueError("polygon area cannot be zero")
    factor = 1.0 / (6.0 * signed_area)
    return centroid_x * factor, centroid_y * factor



def _translate_polygon_to_centroid(
    polygon: list[tuple[float, float, float]],
    target_point: tuple[float, float],
) -> list[tuple[float, float, float]]:
    centroid = _polygon_centroid(polygon)
    dx = target_point[0] - centroid[0]
    dy = target_point[1] - centroid[1]
    return [(x + dx, y + dy, z) for x, y, z in polygon]



def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float, float]]) -> bool:
    x, y = point
    inside = False
    for index in range(len(polygon) - 1):
        x1, y1, _ = polygon[index]
        x2, y2, _ = polygon[index + 1]
        intersects = ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
        )
        if intersects:
            inside = not inside
    return inside



def _segments_intersect(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    def orientation(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])

    def on_segment(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> bool:
        return (
            min(p[0], r[0]) - 1e-9 <= q[0] <= max(p[0], r[0]) + 1e-9
            and min(p[1], r[1]) - 1e-9 <= q[1] <= max(p[1], r[1]) + 1e-9
        )

    o1 = orientation(a1, a2, b1)
    o2 = orientation(a1, a2, b2)
    o3 = orientation(b1, b2, a1)
    o4 = orientation(b1, b2, a2)

    if (o1 > 0 > o2 or o1 < 0 < o2) and (o3 > 0 > o4 or o3 < 0 < o4):
        return True
    if math.isclose(o1, 0.0, abs_tol=1e-9) and on_segment(a1, b1, a2):
        return True
    if math.isclose(o2, 0.0, abs_tol=1e-9) and on_segment(a1, b2, a2):
        return True
    if math.isclose(o3, 0.0, abs_tol=1e-9) and on_segment(b1, a1, b2):
        return True
    if math.isclose(o4, 0.0, abs_tol=1e-9) and on_segment(b1, a2, b2):
        return True
    return False



def _polygons_overlap(
    polygon_a: list[tuple[float, float, float]],
    polygon_b: list[tuple[float, float, float]],
) -> bool:
    for index_a in range(len(polygon_a) - 1):
        a1 = (polygon_a[index_a][0], polygon_a[index_a][1])
        a2 = (polygon_a[index_a + 1][0], polygon_a[index_a + 1][1])
        for index_b in range(len(polygon_b) - 1):
            b1 = (polygon_b[index_b][0], polygon_b[index_b][1])
            b2 = (polygon_b[index_b + 1][0], polygon_b[index_b + 1][1])
            if _segments_intersect(a1, a2, b1, b2):
                return True
    if _point_in_polygon((polygon_a[0][0], polygon_a[0][1]), polygon_b):
        return True
    if _point_in_polygon((polygon_b[0][0], polygon_b[0][1]), polygon_a):
        return True
    return False



def _distance_point_to_segment(
    point: tuple[float, float],
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
) -> float:
    px, py = point
    x1, y1 = segment_start
    x2, y2 = segment_end
    dx = x2 - x1
    dy = y2 - y1
    if math.isclose(dx, 0.0, abs_tol=1e-12) and math.isclose(dy, 0.0, abs_tol=1e-12):
        return math.dist(point, segment_start)
    projection = ((px - x1) * dx + (py - y1) * dy) / ((dx * dx) + (dy * dy))
    projection = max(0.0, min(1.0, projection))
    closest = (x1 + projection * dx, y1 + projection * dy)
    return math.dist(point, closest)



def _minimum_edge_distance(
    polygon_a: list[tuple[float, float, float]],
    polygon_b: list[tuple[float, float, float]],
) -> float:
    minimum = math.inf
    for point in polygon_a[:-1]:
        point_2d = (point[0], point[1])
        for index in range(len(polygon_b) - 1):
            start = (polygon_b[index][0], polygon_b[index][1])
            end = (polygon_b[index + 1][0], polygon_b[index + 1][1])
            minimum = min(minimum, _distance_point_to_segment(point_2d, start, end))
    for point in polygon_b[:-1]:
        point_2d = (point[0], point[1])
        for index in range(len(polygon_a) - 1):
            start = (polygon_a[index][0], polygon_a[index][1])
            end = (polygon_a[index + 1][0], polygon_a[index + 1][1])
            minimum = min(minimum, _distance_point_to_segment(point_2d, start, end))
    return minimum



def _assess_position(
    site_polygon: list[tuple[float, float, float]],
    occupied_polygons: list[list[tuple[float, float, float]]],
    proposed_polygon: list[tuple[float, float, float]],
    clearance: float,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if not all(_point_in_polygon((x, y), site_polygon) for x, y, _ in proposed_polygon[:-1]):
        reasons.append("Building footprint extends outside the site boundary.")

    for index, occupied in enumerate(occupied_polygons, start=1):
        if _polygons_overlap(proposed_polygon, occupied):
            reasons.append(f"Building footprint overlaps placed building {index}.")
            continue
        if clearance > 0 and _minimum_edge_distance(proposed_polygon, occupied) < clearance:
            reasons.append(f"Building footprint violates the {clearance} m clearance to placed building {index}.")

    if not reasons:
        reasons.append("Requested position is geometrically feasible.")
        return True, reasons
    return False, reasons
