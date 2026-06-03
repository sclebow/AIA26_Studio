from __future__ import annotations

import math
from typing import Any

from .multi_building_mock import _normalize_polygon, _point_in_polygon, _polygon_centroid, _segments_intersect as _mock_segments_intersect


MODIFY_BUILDING_BOUNDARY_TOOL_DEFINITION: dict[str, Any] = {
    "name": "modify_building_boundary",
    "description": (
        "Move, orient, rotate, or mirror an existing building boundary and optionally "
        "check whether the transformed footprint still fits inside the site boundary."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "geometry_id": {"type": "string"},
            "boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "description": "Closed building footprint boundary as [x, y, z] coordinates.",
            },
            "target_centroid_xy": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "description": "Absolute centroid target after rotation or mirroring. Takes precedence over translate_by_xy when provided.",
            },
            "translate_by_xy": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "default": [0.0, 0.0],
                "description": "Relative XY translation applied after rotation or mirroring when target_centroid_xy is not provided.",
            },
            "rotation_degrees": {
                "type": "number",
                "default": 0.0,
                "description": "Direct rotation in degrees about rotation_origin_xy or the current centroid.",
            },
            "orientation_degrees": {
                "type": "number",
                "default": 0.0,
                "description": "Alias for rotation_degrees for workflows that phrase the change as orientation.",
            },
            "rotation_origin_xy": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "description": "Optional XY pivot for rotation or mirroring. Defaults to the polygon centroid.",
            },
            "apply_mirror": {
                "type": "boolean",
                "default": False,
                "description": "Mirror the building before translation.",
            },
            "mirror_axis": {
                "type": "string",
                "enum": ["x", "y"],
                "default": "y",
                "description": "Axis used when apply_mirror=true.",
            },
            "site_boundary": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "description": "Optional site boundary used to verify the transformed building remains inside the site.",
            },
            "clearance": {
                "type": "number",
                "default": 0.0,
                "description": "Optional tolerance margin. Positive values require the transformed footprint to remain this far inside the site.",
            },
        },
        "required": ["geometry_id", "boundary"],
    },
}


def modify_building_boundary(
    geometry_id: str,
    boundary: list[list[float]] | list[tuple[float, float, float]],
    target_centroid_xy: list[float] | tuple[float, float] | None = None,
    translate_by_xy: list[float] | tuple[float, float] = (0.0, 0.0),
    rotation_degrees: float = 0.0,
    orientation_degrees: float = 0.0,
    rotation_origin_xy: list[float] | tuple[float, float] | None = None,
    apply_mirror: bool = False,
    mirror_axis: str = "y",
    site_boundary: list[list[float]] | list[tuple[float, float, float]] | None = None,
    clearance: float = 0.0,
) -> dict[str, Any]:
    normalized_boundary = _normalize_polygon(boundary)
    working = list(normalized_boundary)
    transform_origin = _coerce_xy(rotation_origin_xy) if rotation_origin_xy is not None else _polygon_centroid(working)

    if mirror_axis not in {"x", "y"}:
        raise ValueError("mirror_axis must be either 'x' or 'y'")
    if len(translate_by_xy) != 2:
        raise ValueError("translate_by_xy must contain exactly two numbers")
    if target_centroid_xy is not None and len(target_centroid_xy) != 2:
        raise ValueError("target_centroid_xy must contain exactly two numbers")
    if clearance < 0:
        raise ValueError("clearance cannot be negative")

    if apply_mirror:
        working = [_mirror_point_about_origin(point, mirror_axis, transform_origin) for point in working]

    applied_rotation = orientation_degrees if not math.isclose(orientation_degrees, 0.0, abs_tol=1e-9) else rotation_degrees
    if not math.isclose(applied_rotation, 0.0, abs_tol=1e-9):
        working = [_rotate_point_about_origin(point, math.radians(applied_rotation), transform_origin) for point in working]

    current_centroid = _polygon_centroid(working)
    if target_centroid_xy is not None:
        target_centroid = _coerce_xy(target_centroid_xy)
        dx = target_centroid[0] - current_centroid[0]
        dy = target_centroid[1] - current_centroid[1]
    else:
        dx = float(translate_by_xy[0])
        dy = float(translate_by_xy[1])
    transformed = [(x + dx, y + dy, z) for x, y, z in working]

    metrics = _polygon_metrics([(x, y) for x, y, _ in transformed])
    fit_summary = _check_boundary_against_site(transformed, site_boundary, clearance)

    return {
        "success": True,
        "data": {
            "geometry_id": geometry_id,
            "transformed_boundary": [[round(x, 6), round(y, 6), round(z, 6)] for x, y, z in transformed],
            "boundary_area_sqm": round(metrics["area"], 6),
            "perimeter_m": round(metrics["perimeter"], 6),
            "centroid": [round(metrics["centroid"][0], 6), round(metrics["centroid"][1], 6), 0.0],
            "bounding_box": {
                "min": [round(metrics["bbox_min"][0], 6), round(metrics["bbox_min"][1], 6), 0.0],
                "max": [round(metrics["bbox_max"][0], 6), round(metrics["bbox_max"][1], 6), 0.0],
            },
            "transform_parameters": {
                "target_centroid_xy": list(target_centroid_xy) if target_centroid_xy is not None else None,
                "translate_by_xy": [float(translate_by_xy[0]), float(translate_by_xy[1])],
                "rotation_degrees": rotation_degrees,
                "orientation_degrees": orientation_degrees,
                "applied_rotation_degrees": applied_rotation,
                "rotation_origin_xy": [round(transform_origin[0], 6), round(transform_origin[1], 6)],
                "apply_mirror": apply_mirror,
                "mirror_axis": mirror_axis,
                "clearance": clearance,
            },
            **fit_summary,
        },
        "metadata": {
            "tool_name": MODIFY_BUILDING_BOUNDARY_TOOL_DEFINITION["name"],
            "source": "python_mock",
        },
    }


def _check_boundary_against_site(
    boundary: list[tuple[float, float, float]],
    site_boundary: list[list[float]] | list[tuple[float, float, float]] | None,
    clearance: float,
) -> dict[str, Any]:
    if site_boundary is None:
        return {
            "site_boundary_checked": False,
            "fits_within_site_boundary": None,
            "boundary_intersects_site_boundary": None,
            "violations": [],
        }

    site_polygon = _normalize_polygon(site_boundary)
    outside_vertices: list[list[float]] = []
    for x, y, _ in boundary[:-1]:
        if not _point_with_clearance_inside_site((x, y), site_polygon, clearance):
            outside_vertices.append([round(x, 6), round(y, 6), 0.0])

    boundary_intersections = _count_boundary_intersections(boundary, site_polygon)
    violations: list[str] = []
    if outside_vertices:
        violations.append("transformed_building_leaves_site")
    if boundary_intersections > 0:
        violations.append("transformed_building_intersects_site_boundary")

    return {
        "site_boundary_checked": True,
        "fits_within_site_boundary": not outside_vertices and boundary_intersections == 0,
        "boundary_intersects_site_boundary": boundary_intersections > 0,
        "outside_vertices": outside_vertices,
        "site_boundary_intersection_count": boundary_intersections,
        "violations": violations,
    }


def _coerce_xy(point: list[float] | tuple[float, float]) -> tuple[float, float]:
    return (float(point[0]), float(point[1]))


def _polygon_metrics(points: list[tuple[float, float]]) -> dict[str, Any]:
    if len(points) < 4:
        raise ValueError("closed polygon must contain at least three vertices")

    signed_area = 0.0
    centroid_x = 0.0
    centroid_y = 0.0
    perimeter = 0.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    for index in range(len(points) - 1):
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        cross = x1 * y2 - x2 * y1
        signed_area += cross
        centroid_x += (x1 + x2) * cross
        centroid_y += (y1 + y2) * cross
        perimeter += math.dist((x1, y1), (x2, y2))

    signed_area *= 0.5
    area = abs(signed_area)
    if area == 0:
        raise ValueError("polygon area cannot be zero")

    centroid_factor = 1.0 / (6.0 * signed_area)
    centroid = (centroid_x * centroid_factor, centroid_y * centroid_factor)

    return {
        "area": area,
        "perimeter": perimeter,
        "centroid": centroid,
        "bbox_min": (min(xs), min(ys)),
        "bbox_max": (max(xs), max(ys)),
    }


def _mirror_point_about_origin(
    point: tuple[float, float, float],
    axis: str,
    origin: tuple[float, float],
) -> tuple[float, float, float]:
    x, y, z = point
    local_x = x - origin[0]
    local_y = y - origin[1]
    if axis == "x":
        local_y *= -1.0
    else:
        local_x *= -1.0
    return (local_x + origin[0], local_y + origin[1], z)


def _rotate_point_about_origin(
    point: tuple[float, float, float],
    angle_radians: float,
    origin: tuple[float, float],
) -> tuple[float, float, float]:
    x, y, z = point
    local_x = x - origin[0]
    local_y = y - origin[1]
    cos_a = math.cos(angle_radians)
    sin_a = math.sin(angle_radians)
    rotated_x = local_x * cos_a - local_y * sin_a
    rotated_y = local_x * sin_a + local_y * cos_a
    return (rotated_x + origin[0], rotated_y + origin[1], z)


def _point_with_clearance_inside_site(
    point: tuple[float, float],
    site_polygon: list[tuple[float, float, float]],
    clearance: float,
) -> bool:
    if _point_on_polygon_boundary(point, site_polygon):
        return clearance <= 0.0
    if not _point_in_polygon(point, site_polygon):
        return False
    if clearance <= 0.0:
        return True
    return _minimum_distance_to_polygon_edges(point, site_polygon) >= clearance


def _point_on_polygon_boundary(
    point: tuple[float, float],
    polygon: list[tuple[float, float, float]],
) -> bool:
    for index in range(len(polygon) - 1):
        if _point_on_segment(
            point,
            (polygon[index][0], polygon[index][1]),
            (polygon[index + 1][0], polygon[index + 1][1]),
        ):
            return True
    return False


def _point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> bool:
    cross = (point[1] - start[1]) * (end[0] - start[0]) - (point[0] - start[0]) * (end[1] - start[1])
    if not math.isclose(cross, 0.0, abs_tol=1e-9):
        return False
    return (
        min(start[0], end[0]) - 1e-9 <= point[0] <= max(start[0], end[0]) + 1e-9
        and min(start[1], end[1]) - 1e-9 <= point[1] <= max(start[1], end[1]) + 1e-9
    )


def _minimum_distance_to_polygon_edges(
    point: tuple[float, float],
    polygon: list[tuple[float, float, float]],
) -> float:
    return min(
        _distance_point_to_segment(
            point,
            (polygon[index][0], polygon[index][1]),
            (polygon[index + 1][0], polygon[index + 1][1]),
        )
        for index in range(len(polygon) - 1)
    )


def _distance_point_to_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if math.isclose(dx, 0.0, abs_tol=1e-12) and math.isclose(dy, 0.0, abs_tol=1e-12):
        return math.dist(point, start)
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    projected = (start[0] + t * dx, start[1] + t * dy)
    return math.dist(point, projected)


def _count_boundary_intersections(
    boundary: list[tuple[float, float, float]],
    site_polygon: list[tuple[float, float, float]],
) -> int:
    intersections = 0
    for index in range(len(boundary) - 1):
        boundary_start = (boundary[index][0], boundary[index][1])
        boundary_end = (boundary[index + 1][0], boundary[index + 1][1])
        for site_index in range(len(site_polygon) - 1):
            site_start = (site_polygon[site_index][0], site_polygon[site_index][1])
            site_end = (site_polygon[site_index + 1][0], site_polygon[site_index + 1][1])
            if _share_endpoint(boundary_start, boundary_end, site_start, site_end):
                continue
            if _mock_segments_intersect(boundary_start, boundary_end, site_start, site_end):
                intersections += 1
    return intersections


def _share_endpoint(
    a_start: tuple[float, float],
    a_end: tuple[float, float],
    b_start: tuple[float, float],
    b_end: tuple[float, float],
) -> bool:
    points_a = {a_start, a_end}
    points_b = {b_start, b_end}
    return any(math.dist(point_a, point_b) <= 1e-9 for point_a in points_a for point_b in points_b)