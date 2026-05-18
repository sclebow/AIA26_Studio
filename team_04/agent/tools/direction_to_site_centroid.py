from __future__ import annotations

import math
from typing import Any

from .multi_building_mock import _normalize_polygon, _polygon_centroid


DIRECTION_TO_SITE_CENTROID_TOOL_DEFINITION: dict[str, Any] = {
    "name": "direction_to_site_centroid",
    "description": (
        "Compute a movement direction from the current building centroid toward the site centroid "
        "and suggest a bounded translation vector for the next transform step."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
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
            "step_distance": {
                "type": "number",
                "default": 10.0,
                "description": "Maximum XY move distance to suggest for a single step.",
            },
        },
        "required": ["building_boundary", "site_boundary"],
    },
}


def direction_to_site_centroid(
    building_boundary: list[list[float]] | list[tuple[float, float, float]],
    site_boundary: list[list[float]] | list[tuple[float, float, float]],
    step_distance: float = 10.0,
) -> dict[str, Any]:
    if step_distance <= 0:
        raise ValueError("step_distance must be positive")

    normalized_building = _normalize_polygon(building_boundary)
    normalized_site = _normalize_polygon(site_boundary)

    building_centroid = _polygon_centroid(normalized_building)
    site_centroid = _polygon_centroid(normalized_site)
    dx = site_centroid[0] - building_centroid[0]
    dy = site_centroid[1] - building_centroid[1]
    distance = math.hypot(dx, dy)

    if math.isclose(distance, 0.0, abs_tol=1e-9):
        unit_x = 0.0
        unit_y = 0.0
        suggested_dx = 0.0
        suggested_dy = 0.0
    else:
        unit_x = dx / distance
        unit_y = dy / distance
        applied_step = min(step_distance, distance)
        suggested_dx = unit_x * applied_step
        suggested_dy = unit_y * applied_step

    return {
        "success": True,
        "data": {
            "building_centroid": [round(building_centroid[0], 6), round(building_centroid[1], 6), 0.0],
            "site_centroid": [round(site_centroid[0], 6), round(site_centroid[1], 6), 0.0],
            "delta_to_site_centroid": [round(dx, 6), round(dy, 6)],
            "unit_direction": [round(unit_x, 6), round(unit_y, 6)],
            "distance_to_site_centroid": round(distance, 6),
            "step_distance": float(step_distance),
            "suggested_translate_by_xy": [round(suggested_dx, 6), round(suggested_dy, 6)],
        },
        "metadata": {
            "tool_name": DIRECTION_TO_SITE_CENTROID_TOOL_DEFINITION["name"],
            "source": "python_mock",
        },
    }