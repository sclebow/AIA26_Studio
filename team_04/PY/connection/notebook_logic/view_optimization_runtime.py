"""View-optimization runtime — scoring, NSGA-II placement, ranking, shape morphing.

Thin wrappers over the EXISTING optimization/scoring tools, which are the source
of truth (no NSGA-II, scoring, or morphing math is reimplemented here):

    agent.tools.view_optimizer    — sample_valid_placements, rank_placements_by_view,
                                     optimize_view_placement, optimize_two_building_placement,
                                     evaluate_combined_score, list_objectives
    agent.tools.parametric_shape  — shape_variable_spec, apply_shape_variables, build_shape_model

Used by:
  * connection/routes/optimization_routes.py  (/api/optimize, /api/score, /api/rank)
  * test_notebooks/test_view_analysis.ipynb                                  -> validation
"""
from __future__ import annotations

from typing import Any

from . import site_state

from agent.tools.parametric_shape import (
    apply_shape_variables,
    build_shape_model,
    shape_variable_spec,
)
from agent.tools.view_optimizer import (
    evaluate_combined_score,
    list_objectives,
    optimize_two_building_placement,
    optimize_view_placement,
    rank_placements_by_view,
    sample_valid_placements,
)


def _resolve_site_boundary(site_boundary: list[list[float]] | None) -> list[list[float]] | None:
    if site_boundary:
        return site_boundary
    return site_state.load_confirmed_boundary()


# --------------------------------------------------------------------------- #
# Objectives
# --------------------------------------------------------------------------- #
def configure_objectives() -> list[str]:
    """Names of the available optimization objectives."""
    return list_objectives()


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score_view(
    boundary: list[list[float]],
    objective_configs: list[dict[str, Any]],
    *,
    obstacles: list[list[list[float]]],
    site_polygon: Any,
    candidate_polygon: Any,
    **kwargs: Any,
) -> tuple[float, dict[str, float]]:
    """Combined objective score for one candidate boundary."""
    return evaluate_combined_score(
        boundary,
        objective_configs,
        obstacles=obstacles,
        site_polygon=site_polygon,
        candidate_polygon=candidate_polygon,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Placement sampling + ranking
# --------------------------------------------------------------------------- #
def sample_placements(
    boundary: list[list[float]],
    *,
    site_boundary: list[list[float]] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    return sample_valid_placements(boundary, _resolve_site_boundary(site_boundary), **kwargs)


def rank(
    placements: list[dict[str, Any]],
    obstacles: list[list[list[float]]],
    **kwargs: Any,
) -> list[dict[str, Any]]:
    return rank_placements_by_view(placements, obstacles, **kwargs)


# --------------------------------------------------------------------------- #
# Optimization (NSGA-II)
# --------------------------------------------------------------------------- #
def optimize(
    boundary: list[list[float]],
    *,
    obstacles: list[list[list[float]]],
    site_boundary: list[list[float]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Single-building view-placement optimization."""
    return optimize_view_placement(
        boundary=boundary,
        site_boundary=_resolve_site_boundary(site_boundary),
        obstacles=obstacles,
        **kwargs,
    )


def optimize_two(
    boundary_1: list[list[float]],
    boundary_2: list[list[float]],
    *,
    external_obstacles: list[list[list[float]]],
    site_boundary: list[list[float]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Two-building view-placement optimization."""
    return optimize_two_building_placement(
        boundary_1=boundary_1,
        boundary_2=boundary_2,
        site_boundary=_resolve_site_boundary(site_boundary),
        external_obstacles=external_obstacles,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Shape morphing
# --------------------------------------------------------------------------- #
def morph_shape(building_type: str, area: float, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce a parametric shape variant. Returns the variable spec applied with
    the given variables (or the spec's defaults) plus the built shape model."""
    spec = shape_variable_spec(building_type, area)
    applied = apply_shape_variables(spec, variables or {})
    model = build_shape_model(applied) if applied else None
    return {"spec": spec, "applied": applied, "shape_model": model}


# --------------------------------------------------------------------------- #
# Frontend payload
# --------------------------------------------------------------------------- #
def build_optimization_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize an optimize_* result into a frontend-ready option list."""
    data = result.get("data", result) if isinstance(result, dict) else {}
    options = data.get("pareto_solutions") or data.get("saved_options") or data.get("options") or []
    return {
        "options": options,
        "objective_names": data.get("objective_names") or configure_objectives(),
        "best": options[0] if options else None,
        "count": len(options),
    }
