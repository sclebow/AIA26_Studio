from __future__ import annotations

import math
import uuid
from typing import Any


DEFAULT_SITE_COVERAGE_RATIO = 0.35
SUPPORTED_BUILDING_TYPES = ("I", "L", "T", "Y", "H", "X", "O")


TOOL_DEFINITION: dict[str, Any] = {
    "name": "generate_building_boundary",
    "description": (
        "Generate a 2D building footprint boundary from area and optional shape parameters. "
        "Planning-time default assumptions for omitted optional parameters are defined in this tool schema."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "area": {
                "type": "number",
                "description": (
                    "Requested building footprint area in square meters. This parameter is required by the "
                    "runtime tool. In notebook planning flows, if the user does not specify a footprint area, "
                    f"the fallback assumption is {DEFAULT_SITE_COVERAGE_RATIO:.0%} of site area before calling this tool."
                ),
            },
            "building_type": {
                "type": "string",
                "enum": list(SUPPORTED_BUILDING_TYPES),
                "description": "Footprint typology for local boundary generation. Default: I.",
                "default": "I",
            },
            "building_depth": {
                "type": "number",
                "description": "Nominal building depth in meters. Default: 15.0.",
                "default": 15.0,
            },
            "shape_ratio": {
                "type": "number",
                "description": "Controls the split between major and secondary arms for non-rectangular shapes. Default: 0.66.",
                "default": 0.66,
            },
            "location_xy": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "default": [0, 0],
                "description": "Translation applied after local shape construction. Default: [0, 0].",
            },
            "is_mirrored": {
                "type": "boolean",
                "description": "Mirror the footprint before rotation and translation. Uses mirror_axis when provided. Default: false.",
                "default": False,
            },
            "mirror_axis": {
                "type": "string",
                "enum": ["x", "y"],
                "description": "Axis used when is_mirrored=true. Default: y.",
                "default": "y",
            },
            "rotation_degrees": {
                "type": "number",
                "description": "Direct rotation in degrees applied before translation. Takes precedence over rotation step fields.",
                "default": 0.0,
            },
            "orientation_degrees": {
                "type": "number",
                "description": "Alias for rotation_degrees for prompts that use orientation language. Default: 0.",
                "default": 0.0,
            },
            "max_rotation_angle": {
                "type": "number",
                "description": (
                    "Maximum rotation range in degrees used with rotation_step and max_rotation_step. "
                    "Applied angle = (max_rotation_angle / max_rotation_step) * rotation_step when max_rotation_step > 1, "
                    "or exactly max_rotation_angle when max_rotation_step=1 and rotation_step=1. "
                    "Example: to request a 45 degree rotation in one step, set max_rotation_angle=45, "
                    "max_rotation_step=1, rotation_step=1. Default: 180."
                ),
                "default": 180,
            },
            "max_rotation_step": {
                "type": "integer",
                "description": (
                    "Number of discrete rotation steps spanning max_rotation_angle. "
                    "Agents should choose this from the requested angle resolution. "
                    "Example: for a single 45 degree turn, use max_rotation_step=1 with max_rotation_angle=45. Default: 4."
                ),
                "default": 4,
            },
            "rotation_step": {
                "type": "integer",
                "description": (
                    "Selected discrete rotation step index. Use 0 for no rotation. "
                    "Example: for a single requested 45 degree rotation, use rotation_step=1 with max_rotation_angle=45 and max_rotation_step=1. Default: 0."
                ),
                "default": 0,
            },
        },
        "required": ["area"],
    },
}


def get_default_tool_arguments() -> dict[str, Any]:
    properties = TOOL_DEFINITION["inputSchema"]["properties"]
    return {
        name: properties[name]["default"]
        for name in (
            "building_type",
            "building_depth",
            "shape_ratio",
            "location_xy",
            "is_mirrored",
            "mirror_axis",
            "rotation_degrees",
            "orientation_degrees",
            "max_rotation_angle",
            "max_rotation_step",
            "rotation_step",
        )
    }


def get_boundary_planning_defaults() -> dict[str, Any]:
    return {
        "default_site_coverage_ratio": DEFAULT_SITE_COVERAGE_RATIO,
        "tool_argument_defaults": get_default_tool_arguments(),
    }


def generate_building_boundary(
    area: float,
    building_type: str = "I",
    building_depth: float = 15.0,
    shape_ratio: float = 0.66,
    location_xy: tuple[float, float] | list[float] = (0.0, 0.0),
    is_mirrored: bool = False,
    mirror_axis: str = "y",
    rotation_degrees: float = 0.0,
    orientation_degrees: float = 0.0,
    max_rotation_angle: float = 180.0,
    max_rotation_step: int = 4,
    rotation_step: int = 0,
) -> dict[str, Any]:
    if area <= 0:
        raise ValueError("area must be greater than 0")
    if building_depth <= 0:
        raise ValueError("building_depth must be greater than 0")
    if building_type not in SUPPORTED_BUILDING_TYPES:
        raise ValueError(f"building_type must be one of: {', '.join(SUPPORTED_BUILDING_TYPES)}")
    if not 0 < shape_ratio < 1:
        raise ValueError("shape_ratio must be between 0 and 1")
    if mirror_axis not in {"x", "y"}:
        raise ValueError("mirror_axis must be either 'x' or 'y'")
    if max_rotation_step < 0:
        raise ValueError("max_rotation_step cannot be negative")
    if rotation_step < 0:
        raise ValueError("rotation_step cannot be negative")

    local_boundary = _build_local_boundary(
        area=area,
        building_type=building_type,
        building_depth=building_depth,
        shape_ratio=shape_ratio,
    )

    transformed = list(local_boundary)
    if is_mirrored:
        transformed = [_mirror_point(point, mirror_axis) for point in transformed]

    direct_angle = orientation_degrees if not math.isclose(orientation_degrees, 0.0, abs_tol=1e-9) else rotation_degrees
    if not math.isclose(direct_angle, 0.0, abs_tol=1e-9):
        angle = direct_angle
        transformed = [_rotate_point(point, math.radians(angle)) for point in transformed]
    elif max_rotation_angle > 0 and max_rotation_step >= 1 and 0 < rotation_step <= max_rotation_step:
        angle = (max_rotation_angle / max_rotation_step) * rotation_step
        transformed = [_rotate_point(point, math.radians(angle)) for point in transformed]
    else:
        angle = 0.0

    if len(location_xy) != 2:
        raise ValueError("location_xy must contain exactly two numbers")
    translated = [(x + float(location_xy[0]), y + float(location_xy[1])) for x, y in transformed]

    metrics = _polygon_metrics(translated)
    return {
        "success": True,
        "data": {
            "geometry_id": f"generate_building_boundary_{uuid.uuid4().hex[:12]}",
            "shape_type": building_type,
            "boundary": [[round(x, 6), round(y, 6), 0.0] for x, y in translated],
            "boundary_area_sqm": round(metrics["area"], 6),
            "perimeter_m": round(metrics["perimeter"], 6),
            "centroid": [round(metrics["centroid"][0], 6), round(metrics["centroid"][1], 6), 0.0],
            "bounding_box": {
                "min": [round(metrics["bbox_min"][0], 6), round(metrics["bbox_min"][1], 6), 0.0],
                "max": [round(metrics["bbox_max"][0], 6), round(metrics["bbox_max"][1], 6), 0.0],
            },
            "parameters": {
                "area": area,
                "building_type": building_type,
                "building_depth": building_depth,
                "shape_ratio": shape_ratio,
                "location_xy": [float(location_xy[0]), float(location_xy[1])],
                "is_mirrored": is_mirrored,
                "mirror_axis": mirror_axis,
                "rotation_degrees": rotation_degrees,
                "orientation_degrees": orientation_degrees,
                "max_rotation_angle": max_rotation_angle,
                "max_rotation_step": max_rotation_step,
                "rotation_step": rotation_step,
                "applied_rotation_angle": angle,
            },
        },
        "metadata": {
            "tool_name": TOOL_DEFINITION["name"],
            "source": "python",
        },
    }


def _build_local_boundary(
    area: float,
    building_type: str,
    building_depth: float,
    shape_ratio: float,
) -> list[tuple[float, float]]:
    baseline_length = area / building_depth
    half_depth = building_depth / 2.0

    if building_type == "I":
        half_length = baseline_length / 2.0
        return _close_polygon(
            [
                (-half_length, -half_depth),
                (half_length, -half_depth),
                (half_length, half_depth),
                (-half_length, half_depth),
            ]
        )

    if building_type == "L":
        return _scaled_template_polygon(
            area,
            [
                (-3.0, -1.0),
                (3.0, -1.0),
                (3.0, 1.0),
                (-1.0, 1.0),
                (-1.0, 3.0),
                (-3.0, 3.0),
            ],
        )

    horizontal_length = baseline_length * shape_ratio
    vertical_length = baseline_length - horizontal_length
    if horizontal_length <= 0 or vertical_length <= 0:
        raise ValueError("area, building_depth, and shape_ratio produce an invalid footprint")

    if building_type == "T":
        horizontal_half = horizontal_length / 2.0
        return _close_polygon(
            [
                (-horizontal_half, -half_depth),
                (horizontal_half, -half_depth),
                (horizontal_half, half_depth),
                (half_depth, half_depth),
                (half_depth, vertical_length + half_depth),
                (-half_depth, vertical_length + half_depth),
                (-half_depth, half_depth),
                (-horizontal_half, half_depth),
            ]
        )

    if building_type == "H":
        return _scaled_template_polygon(
            area,
            [
                (-3.0, -3.0),
                (-1.6, -3.0),
                (-1.6, -0.8),
                (1.6, -0.8),
                (1.6, -3.0),
                (3.0, -3.0),
                (3.0, 3.0),
                (1.6, 3.0),
                (1.6, 0.8),
                (-1.6, 0.8),
                (-1.6, 3.0),
                (-3.0, 3.0),
            ],
        )

    if building_type == "O":
        return _scaled_template_polygon(
            area,
            [
                (-2.0, -1.0),
                (-1.0, -2.0),
                (1.0, -2.0),
                (2.0, -1.0),
                (2.0, 1.0),
                (1.0, 2.0),
                (-1.0, 2.0),
                (-2.0, 1.0),
            ],
        )

    if building_type == "X":
        return _scaled_template_polygon(
            area,
            [
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
        )

    if building_type == "Y":
        return _scaled_template_polygon(
            area,
            [
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
        )
    raise ValueError(f"unsupported building_type: {building_type}")


def _close_polygon(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not points:
        raise ValueError("polygon requires at least one point")
    if points[0] == points[-1]:
        return points
    return points + [points[0]]


def _scaled_template_polygon(area: float, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    closed = _close_polygon(points)
    metrics = _polygon_metrics(closed)
    scale = math.sqrt(area / metrics["area"])
    return [(x * scale, y * scale) for x, y in closed]


def _mirror_point(point: tuple[float, float], axis: str) -> tuple[float, float]:
    x, y = point
    if axis == "x":
        return (x, -y)
    return (-x, y)


def _rotate_point(point: tuple[float, float], angle_radians: float) -> tuple[float, float]:
    x, y = point
    cos_a = math.cos(angle_radians)
    sin_a = math.sin(angle_radians)
    return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)


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