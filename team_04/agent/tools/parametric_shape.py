"""Area-preserving wing-parametric building shapes for optimizer use.

Instead of a raw stretch (which distorts all vertices uniformly), this module
parameterises a building as a set of rectangular wings:

  building_depth  — wing thickness (all wings share the same depth)
  shape_ratio     — how total area is distributed between wings
  end_wing_rotation_i — each LEAF wing (free arm with one junction) can be
                         rotated around the junction without changing its area

Area is always exactly target_area because `build_shape_model` accepts area as
a hard parameter.  Wing thickness is preserved because length changes instead.

Supported types:  I (rect), L, T, U, H  — anything in SUPPORTED_WINGED_BUILDING_TYPES.
"""
from __future__ import annotations

import math
from typing import Any

from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .building_shape_graph import (
    SUPPORTED_WINGED_BUILDING_TYPES,
    ShapeModel,
    WingModel,
    build_shape_model,
)

# depth range to avoid degenerate slivers or too-chunky forms
_DEPTH_MIN = 5.0
_DEPTH_MAX = 25.0
_ROT_RANGE  = 45.0   # degrees, per end wing


# ---------------------------------------------------------------------------
# Public API used by the optimizer
# ---------------------------------------------------------------------------

def shape_variable_spec(
    building_type: str,
    target_area: float,
) -> dict[str, Any]:
    """
    Return the variable bounds for wing-parametric shape optimisation.

    Returns a dict with keys: names, lower, upper, leaf_wing_indices.

    Variables (in order):
      [0]  building_depth    ∈ [_DEPTH_MIN, _DEPTH_MAX]
      [1]  shape_ratio       ∈ [0.05, 0.95]
      [2…] end_rot_<i>       ∈ [-_ROT_RANGE, +_ROT_RANGE]  — one per leaf wing
    """
    btype = building_type.upper()
    leaf_indices = _leaf_wing_indices_for(btype, target_area)

    names  = ["building_depth", "shape_ratio"] + [f"end_rot_{i}" for i in range(len(leaf_indices))]
    lower  = [_DEPTH_MIN, 0.05]               + [-_ROT_RANGE]   * len(leaf_indices)
    upper  = [_DEPTH_MAX, 0.95]               + [ _ROT_RANGE]   * len(leaf_indices)

    return {
        "names":             names,
        "lower":             lower,
        "upper":             upper,
        "n_shape_vars":      len(names),
        "leaf_wing_indices": leaf_indices,
    }


def apply_shape_variables(
    building_type: str,
    target_area: float,
    variables: list[float],
    leaf_wing_indices: list[int],
) -> Polygon:
    """
    Build a centred Shapely polygon from shape variables.

    variables = [building_depth, shape_ratio, end_rot_0, end_rot_1, ...]
    Area equals target_area exactly.  Wing thickness equals building_depth.
    End-wing arms can rotate ±_ROT_RANGE degrees around their junction.
    """
    depth = float(max(_DEPTH_MIN, min(_DEPTH_MAX, variables[0])))
    ratio = float(max(0.05,       min(0.95,        variables[1])))
    end_rotations = {
        idx: float(variables[2 + k])
        for k, idx in enumerate(leaf_wing_indices)
        if (2 + k) < len(variables)
    }
    return _build_wing_polygon(
        building_type=building_type,
        target_area=target_area,
        building_depth=depth,
        shape_ratio=ratio,
        end_wing_rotations=end_rotations,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_wing_polygon(
    building_type: str,
    target_area: float,
    *,
    building_depth: float,
    shape_ratio: float,
    end_wing_rotations: dict[int, float] | None = None,
) -> Polygon:
    btype = building_type.upper()
    model = build_shape_model(
        area=target_area,
        building_type=btype,
        building_depth=building_depth,
        shape_ratio=shape_ratio,
    )

    if not end_wing_rotations:
        return model.polygon

    leaf_set = set(_leaf_wing_indices_for(btype, target_area))
    wings_list = list(model.wings)

    for i, wing in enumerate(wings_list):
        rot = end_wing_rotations.get(wing.index)
        if rot is None or math.isclose(rot, 0.0, abs_tol=1e-9):
            continue
        if wing.index not in leaf_set:
            continue
        pivot = _junction_pivot(wing, model.wings)
        rotated_poly = affinity.rotate(wing.polygon, rot, origin=pivot, use_radians=False)
        wings_list[i] = WingModel(
            index=wing.index,
            role=wing.role,
            polygon=rotated_poly,
            nominal_width=wing.nominal_width,
            nominal_length=wing.nominal_length,
            editable_parameters=wing.editable_parameters,
        )

    union = unary_union([w.polygon for w in wings_list])
    if not isinstance(union, Polygon):
        union = union.buffer(0)
    if not isinstance(union, Polygon):
        return model.polygon  # fallback: no rotation

    centroid = union.centroid
    return affinity.translate(union, xoff=-centroid.x, yoff=-centroid.y)


def _leaf_wing_indices_for(building_type: str, target_area: float) -> list[int]:
    """Return sorted leaf-wing indices (those with ≤1 junction) for the given type."""
    btype = building_type.upper()
    if btype not in SUPPORTED_WINGED_BUILDING_TYPES:
        return []
    try:
        model = build_shape_model(
            area=target_area,
            building_type=btype,
            building_depth=10.0,
            shape_ratio=0.5,
        )
    except Exception:
        return []
    degree: dict[int, int] = {w.index: 0 for w in model.wings}
    for a, b in model.edge_pairs:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    return sorted(idx for idx, deg in degree.items() if deg <= 1)


def _junction_pivot(
    wing: WingModel,
    all_wings: tuple[WingModel, ...],
) -> tuple[float, float]:
    """
    Pivot for end-wing rotation = centroid of the intersection with the adjacent wing.
    Falls back to wing centroid if no intersection is found.
    """
    for other in all_wings:
        if other.index == wing.index:
            continue
        inter = wing.polygon.intersection(other.polygon)
        if inter.area > 1e-6:
            c = inter.centroid
            return (float(c.x), float(c.y))
    c = wing.polygon.centroid
    return (float(c.x), float(c.y))
