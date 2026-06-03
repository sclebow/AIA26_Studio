from __future__ import annotations

import math
import uuid
from typing import Any

from .building_shape_graph import apply_shape_transform, build_shape_model, serialize_shape_model, shape_model_boundary_points
from .placement_optimizer import evaluate_boundary_fit, optimize_boundary_placement


DEFAULT_SITE_COVERAGE_RATIO = 0.35
SUPPORTED_BUILDING_TYPES = ("I", "L", "T", "U", "Y", "H", "X", "O")


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
                "description": "Controls the split between major and secondary wings for non-rectangular shapes. Default: 0.66.",
                "default": 0.66,
            },
            "location_xy": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "default": [0, 0],
                "description": (
                    "Translation applied after local shape construction. When site_boundary is supplied with "
                    "optimize_placement=true, this acts as a centroid preference instead of a direct translation. Default: [0, 0]."
                ),
            },
            "site_boundary": {
                "type": "array",
                "description": "Optional site boundary polyline. When supplied, the tool can optimize placement inside the site.",
            },
            "optimize_placement": {
                "type": "boolean",
                "description": "Use pymoo to place the generated footprint inside site_boundary when site data is available. Default: true.",
                "default": True,
            },
            "placement_clearance": {
                "type": "number",
                "description": "Minimum preferred clearance from the site edge during placement optimization. Default: 0.",
                "default": 0.0,
            },
            "population_size": {
                "type": "integer",
                "description": "Population size for the pymoo GA placement search. Default: 40.",
                "default": 40,
            },
            "generation_count": {
                "type": "integer",
                "description": "Number of generations for the pymoo GA placement search. Default: 60.",
                "default": 60,
            },
            "random_seed": {
                "type": "integer",
                "description": "Random seed used by the pymoo GA placement search. Default: 7.",
                "default": 7,
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
            "optimize_placement",
            "placement_clearance",
            "population_size",
            "generation_count",
            "random_seed",
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
    site_boundary: list[list[float]] | list[tuple[float, float]] | None = None,
    optimize_placement: bool = True,
    placement_clearance: float = 0.0,
    population_size: int = 40,
    generation_count: int = 60,
    random_seed: int = 7,
    is_mirrored: bool = False,
    mirror_axis: str = "y",
    rotation_degrees: float = 0.0,
    orientation_degrees: float = 0.0,
    max_rotation_angle: float = 180.0,
    max_rotation_step: int = 4,
    rotation_step: int = 0,
) -> dict[str, Any]:
    normalized_type = building_type.upper()
    if area <= 0:
        raise ValueError("area must be greater than 0")
    if building_depth <= 0:
        raise ValueError("building_depth must be greater than 0")
    if normalized_type not in SUPPORTED_BUILDING_TYPES:
        raise ValueError(f"building_type must be one of: {', '.join(SUPPORTED_BUILDING_TYPES)}")
    if not 0 < shape_ratio < 1:
        raise ValueError("shape_ratio must be between 0 and 1")
    if mirror_axis not in {"x", "y"}:
        raise ValueError("mirror_axis must be either 'x' or 'y'")
    if placement_clearance < 0:
        raise ValueError("placement_clearance cannot be negative")
    if population_size < 4:
        raise ValueError("population_size must be at least 4")
    if generation_count < 1:
        raise ValueError("generation_count must be at least 1")
    if max_rotation_step < 0:
        raise ValueError("max_rotation_step cannot be negative")
    if rotation_step < 0:
        raise ValueError("rotation_step cannot be negative")
    if len(location_xy) != 2:
        raise ValueError("location_xy must contain exactly two numbers")

    local_model = build_shape_model(
        area=area,
        building_type=normalized_type,
        building_depth=building_depth,
        shape_ratio=shape_ratio,
    )
    requested_angle, fixed_rotation = _resolve_requested_rotation(
        rotation_degrees=rotation_degrees,
        orientation_degrees=orientation_degrees,
        max_rotation_angle=max_rotation_angle,
        max_rotation_step=max_rotation_step,
        rotation_step=rotation_step,
    )
    target_location = (float(location_xy[0]), float(location_xy[1]))
    placement_summary: dict[str, Any] = {}

    if site_boundary:
        mirrored_model = apply_shape_transform(
            local_model,
            is_mirrored=is_mirrored,
            mirror_axis=mirror_axis,
        )
        location_hint = None if _is_origin(target_location) else target_location
        if optimize_placement:
            placement_summary = optimize_boundary_placement(
                boundary=shape_model_boundary_points(mirrored_model),
                site_boundary=site_boundary,
                fixed_rotation_degrees=fixed_rotation,
                rotation_limit_degrees=max_rotation_angle,
                target_location_xy=location_hint,
                clearance_target=placement_clearance,
                population_size=population_size,
                generation_count=generation_count,
                random_seed=random_seed,
            )
            transformed_model = apply_shape_transform(
                mirrored_model,
                translation_xy=(float(placement_summary["centroid_xy"][0]), float(placement_summary["centroid_xy"][1])),
                rotation_degrees=float(placement_summary["rotation_degrees"]),
            )
            applied_angle = float(placement_summary["rotation_degrees"])
        else:
            transformed_model = apply_shape_transform(
                local_model,
                translation_xy=target_location,
                rotation_degrees=requested_angle,
                is_mirrored=is_mirrored,
                mirror_axis=mirror_axis,
            )
            applied_angle = requested_angle
            placement_summary = {"optimized": False}
        site_fit_summary = evaluate_boundary_fit(
            boundary=shape_model_boundary_points(transformed_model),
            site_boundary=site_boundary,
            clearance_target=placement_clearance,
        )
    else:
        transformed_model = apply_shape_transform(
            local_model,
            translation_xy=target_location,
            rotation_degrees=requested_angle,
            is_mirrored=is_mirrored,
            mirror_axis=mirror_axis,
        )
        applied_angle = requested_angle
        site_fit_summary = {}

    payload = serialize_shape_model(transformed_model)
    return {
        "success": True,
        "data": {
            "geometry_id": f"generate_building_boundary_{uuid.uuid4().hex[:12]}",
            "shape_type": normalized_type,
            **payload,
            "site_fit_summary": site_fit_summary,
            "placement_optimization": placement_summary,
            "parameters": {
                "area": area,
                "building_type": normalized_type,
                "building_depth": building_depth,
                "shape_ratio": shape_ratio,
                "location_xy": [float(location_xy[0]), float(location_xy[1])],
                "site_boundary_supplied": bool(site_boundary),
                "optimize_placement": optimize_placement,
                "placement_clearance": placement_clearance,
                "population_size": population_size,
                "generation_count": generation_count,
                "random_seed": random_seed,
                "is_mirrored": is_mirrored,
                "mirror_axis": mirror_axis,
                "rotation_degrees": rotation_degrees,
                "orientation_degrees": orientation_degrees,
                "max_rotation_angle": max_rotation_angle,
                "max_rotation_step": max_rotation_step,
                "rotation_step": rotation_step,
                "applied_rotation_angle": applied_angle,
            },
        },
        "metadata": {
            "tool_name": TOOL_DEFINITION["name"],
            "source": "python",
        },
    }


def _resolve_requested_rotation(
    *,
    rotation_degrees: float,
    orientation_degrees: float,
    max_rotation_angle: float,
    max_rotation_step: int,
    rotation_step: int,
) -> tuple[float, float | None]:
    if not math.isclose(orientation_degrees, 0.0, abs_tol=1e-9):
        return float(orientation_degrees), float(orientation_degrees)
    if not math.isclose(rotation_degrees, 0.0, abs_tol=1e-9):
        return float(rotation_degrees), float(rotation_degrees)
    if max_rotation_angle > 0 and max_rotation_step >= 1 and 0 < rotation_step <= max_rotation_step:
        angle = (max_rotation_angle / max_rotation_step) * rotation_step
        return float(angle), float(angle)
    if max_rotation_angle <= 0:
        return 0.0, 0.0
    return 0.0, None


def _is_origin(location_xy: tuple[float, float]) -> bool:
    return math.isclose(location_xy[0], 0.0, abs_tol=1e-9) and math.isclose(location_xy[1], 0.0, abs_tol=1e-9)
