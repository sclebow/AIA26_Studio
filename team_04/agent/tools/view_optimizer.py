"""Multi-objective view placement optimizer — pymoo NSGA-II.

Shape morphing
--------------
Set ``building_type`` (e.g. "L", "T", "U") and ``optimize_shape=True`` to add
wing-parametric shape variables instead of the old stretch hack:

  building_depth ∈ [5, 25]   — wing thickness (all wings same depth)
  shape_ratio    ∈ [0.05, 0.95] — how area splits between wings
  end_rot_i      ∈ [-45, 45] — rotate leaf (free-arm) wings around their junction

Area is always exactly target_area.  Wing thickness is preserved.  The polygon
character (L stays L, T stays T) is preserved.

Extensible objectives
---------------------
Pass ``objective_configs`` to add any combination from OBJECTIVE_REGISTRY:

  objective_configs = [
      {"name": "unblocked_view", "weight": 0.7},
      {"name": "attractor_view", "weight": 0.3, "attractors": [...]},
      {"name": "clearance_from_site", "weight": 0.1},
  ]

Combined score per building = Σ (weight_i × score_i), normalised to [0,1].
NSGA-II Pareto front is always over the combined scores of the two buildings.
Single-building NSGA-II uses F=[unblocked, attractor] when attractor supplied,
or F=[combined, clearance] otherwise.

Adding a new objective: add a function to OBJECTIVE_REGISTRY below.  The LLM
can then reference it by name in a tool call.

Seed-point flow (unchanged)
---------------------------
  1. sample_valid_placements()   — grid × rotation sweep, inside-site filter
  2. rank_placements_by_view()   — evaluate and sort candidates
  3. optimize_view_placement()   — single-building 2-obj NSGA-II
  4. optimize_two_building_placement()  — joint 2-building NSGA-II
"""
from __future__ import annotations

import math
from typing import Any, Callable

from shapely import affinity
from shapely.geometry import Polygon

from .parametric_shape import apply_shape_variables, shape_variable_spec
from .site_setback import clearance_constraint_value, compute_buildable_zone
from .view_analysis import (
    _coerce_polygon_2d,
    evaluate_attractor_views,
    evaluate_building_views,
)

_PYMOO_IMPORT_ERROR: Exception | None = None

try:
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.core.problem import ElementwiseProblem
    from pymoo.optimize import minimize as pymoo_minimize
except Exception as exc:  # pragma: no cover
    NSGA2 = None  # type: ignore[assignment,misc]
    ElementwiseProblem = None  # type: ignore[assignment,misc]
    pymoo_minimize = None  # type: ignore[assignment]
    _PYMOO_IMPORT_ERROR = exc


# ---------------------------------------------------------------------------
# Objective registry
# ---------------------------------------------------------------------------
# Each function receives keyword arguments from _eval_context() and returns
# a score in [0, 1].  Add new objectives here; reference them by name in
# objective_configs.

def _obj_unblocked_view(
    boundary: list[list[float]],
    *,
    obstacles: list[list[list[float]]],
    piece_length: float,
    ray_length: float,
    **_: Any,
) -> float:
    r = evaluate_building_views(boundary, obstacles,
                                piece_length=piece_length, ray_length=ray_length,
                                return_ray_detail=False)
    return r["view_score"]


def _obj_attractor_view(
    boundary: list[list[float]],
    *,
    obstacles: list[list[list[float]]],
    piece_length: float,
    attractors: list[dict[str, Any]] | None = None,
    **_: Any,
) -> float:
    if not attractors:
        return 0.0
    r = evaluate_attractor_views(boundary, attractors, obstacles,
                                 piece_length=piece_length, return_ray_detail=False)
    return r["attractor_score"]


def _obj_clearance_from_site(
    boundary: list[list[float]],
    *,
    site_polygon: Polygon,
    candidate_polygon: Polygon,
    **_: Any,
) -> float:
    raw = site_polygon.boundary.distance(candidate_polygon)
    # Normalise roughly to [0, 1] using site bounding box diagonal
    diag = math.hypot(*(site_polygon.bounds[2] - site_polygon.bounds[0],
                        site_polygon.bounds[3] - site_polygon.bounds[1]))
    return float(min(1.0, raw / max(diag * 0.1, 1.0)))


def _obj_clearance_from_obstacles(
    boundary: list[list[float]],
    *,
    candidate_polygon: Polygon,
    obstacle_polys: list[Polygon] | None = None,
    **_: Any,
) -> float:
    if not obstacle_polys:
        return 1.0
    min_dist = min(candidate_polygon.distance(obs) for obs in obstacle_polys)
    # Normalise: 20 m+ is near-perfect clearance
    return float(min(1.0, min_dist / 20.0))


def _obj_sky_exposure(
    boundary: list[list[float]],
    *,
    obstacles: list[list[list[float]]],
    piece_length: float,
    ray_length: float,
    **_: Any,
) -> float:
    """Fraction of boundary test points that have at least one unblocked ray (alias of unblocked_view)."""
    return _obj_unblocked_view(boundary, obstacles=obstacles,
                               piece_length=piece_length, ray_length=ray_length)


def _obj_sun_avoidance(
    boundary: list[list[float]],
    *,
    obstacles: list[list[list[float]]],
    piece_length: float,
    sun_vectors: list[dict[str, float]] | None = None,
    **_: Any,
) -> float:
    """Phase 1: reward facades that *avoid* the worst sun.

    Returns ``1 - sun_exposure_score`` so it slots into the higher-is-better
    combined-score pattern (the exposure score itself is lower-is-better). Other
    placed buildings arrive via ``obstacles`` and act as mutual-shading
    obstacles, exactly like the view-objective obstacle pattern.
    """
    if not sun_vectors:
        return 1.0
    from .sun_analysis import evaluate_sun_exposure
    r = evaluate_sun_exposure(boundary, sun_vectors, obstacles,
                              piece_length=piece_length, return_ray_detail=False)
    return float(max(0.0, 1.0 - r["sun_exposure_score"]))


def _obj_grid_alignment(
    boundary: list[list[float]],
    *,
    grid: dict[str, Any] | None = None,
    **_: Any,
) -> float:
    """Phase 3: 1.0 when the footprint's long edge is parallel to the site grid."""
    if not grid:
        return 0.0
    from .site_grid import alignment_score
    return alignment_score(boundary, grid)


def _obj_boundary_proximity(
    boundary: list[list[float]],
    *,
    site_polygon: Polygon,
    candidate_polygon: Polygon,
    reference_line: list[list[float]] | None = None,
    max_distance: float = 30.0,
    **_: Any,
) -> float:
    """Phase 3: reward *hugging* the frontage — high when the building sits close
    to the chosen side (or the site boundary). Drives the "commercial buildings
    line the street" rule via a use-weighted objective.
    """
    if reference_line:
        from shapely.geometry import LineString as _LS
        ref = _LS([(float(p[0]), float(p[1])) for p in reference_line])
        dist = ref.distance(candidate_polygon)
    else:
        dist = site_polygon.boundary.distance(candidate_polygon)
    return float(max(0.0, 1.0 - dist / max(max_distance, 1e-6)))


OBJECTIVE_REGISTRY: dict[str, Callable[..., float]] = {
    "unblocked_view":         _obj_unblocked_view,
    "attractor_view":         _obj_attractor_view,
    "clearance_from_site":    _obj_clearance_from_site,
    "clearance_from_obstacles": _obj_clearance_from_obstacles,
    "sky_exposure":            _obj_sky_exposure,
    "sun_avoidance":           _obj_sun_avoidance,
    "grid_alignment":          _obj_grid_alignment,
    "boundary_proximity":      _obj_boundary_proximity,
}


def list_objectives() -> list[str]:
    """Return all registered objective names."""
    return sorted(OBJECTIVE_REGISTRY)


def evaluate_combined_score(
    boundary: list[list[float]],
    objective_configs: list[dict[str, Any]],
    *,
    obstacles: list[list[list[float]]],
    site_polygon: Polygon,
    candidate_polygon: Polygon,
    obstacle_polys: list[Polygon] | None = None,
    piece_length: float = 2.0,
    ray_length: float = 100.0,
) -> tuple[float, dict[str, float]]:
    """
    Evaluate all objectives and return (combined_score, per_objective_scores).

    combined_score = Σ(weight_i × score_i) / Σ weight_i  — weighted average.
    """
    context = dict(
        obstacles=obstacles,
        site_polygon=site_polygon,
        candidate_polygon=candidate_polygon,
        obstacle_polys=obstacle_polys or [],
        piece_length=piece_length,
        ray_length=ray_length,
    )
    # Add per-objective extra params (e.g. attractors)
    for cfg in objective_configs:
        for k, v in cfg.items():
            if k not in ("name", "weight") and k not in context:
                context[k] = v

    total_weight = 0.0
    weighted_sum = 0.0
    per_obj: dict[str, float] = {}

    for cfg in objective_configs:
        name = cfg["name"]
        weight = float(cfg.get("weight", 1.0))
        fn = OBJECTIVE_REGISTRY.get(name)
        if fn is None:
            continue
        # Merge cfg-level params into context (e.g. per-objective attractors)
        call_ctx = dict(context)
        for k, v in cfg.items():
            if k not in ("name", "weight"):
                call_ctx[k] = v
        score = float(fn(boundary, **call_ctx))
        per_obj[name] = round(score, 6)
        weighted_sum += weight * score
        total_weight += weight

    combined = weighted_sum / total_weight if total_weight > 0 else 0.0
    return round(combined, 6), per_obj


# ---------------------------------------------------------------------------
# Convenience: build default objective_configs from legacy params
# ---------------------------------------------------------------------------

def _default_objective_configs(
    attractors: list[dict[str, Any]] | None,
    attractor_weight: float,
    sun_vectors: list[dict[str, float]] | None = None,
    sun_weight: float = 0.0,
) -> list[dict[str, Any]]:
    cfgs: list[dict[str, Any]] = []
    if attractors:
        w_view = max(0.0, 1.0 - attractor_weight)
        cfgs.append({"name": "unblocked_view", "weight": w_view})
        cfgs.append({"name": "attractor_view", "weight": float(attractor_weight), "attractors": attractors})
    else:
        cfgs.append({"name": "unblocked_view", "weight": 1.0})
    if sun_vectors and sun_weight > 0.0:
        cfgs.append({"name": "sun_avoidance", "weight": float(sun_weight), "sun_vectors": sun_vectors})
    return cfgs


# ---------------------------------------------------------------------------
# Step 1: Seed-point pre-computation
# ---------------------------------------------------------------------------

def sample_valid_placements(
    boundary: list[list[float]],
    site_boundary: list[list[float]],
    *,
    rotation_step_degrees: int = 10,
    grid_step: float = 5.0,
    site_setbacks: dict[str, Any] | None = None,
    grid: dict[str, Any] | None = None,
    orientation_offsets_deg: tuple[float, ...] = (),
) -> list[dict[str, Any]]:
    """
    Return every discrete (centroid, rotation) pair where the building fits
    entirely inside the buildable zone (site minus setbacks).

    Two modes:

    * **Free sweep (default):** an axis-aligned ``grid_step`` lattice × every
      ``rotation_step_degrees`` rotation — the original behaviour.
    * **Site-grid aligned (Phase 3):** pass a ``grid`` from
      ``site_grid.derive_site_grid`` and placement is restricted to the grid's
      seed nodes × the discrete {parallel, perpendicular} orientations
      (``site_grid.aligned_orientations``). Buildings no longer rotate freely —
      they sit on the grid, parallel to the chosen side, like real plots.

    Args:
        site_setbacks: Optional dict passed to ``compute_buildable_zone``.
                       Keys: ``default_setback``, ``edge_setbacks``,
                       ``edge_road_widths``, ``road_setback_ratio``, ``min_setback``.
        grid: Optional site grid; switches to aligned-placement mode.
        orientation_offsets_deg: Extra ± offsets added to the aligned set when a
                       brief explicitly permits looser orientation.
    """
    base_polygon = _coerce_polygon_2d(boundary)
    site_polygon = _coerce_polygon_2d(site_boundary)

    if site_setbacks:
        buildable_zone = compute_buildable_zone(site_boundary, **site_setbacks)
    else:
        buildable_zone = site_polygon

    candidates: list[dict[str, Any]] = []

    if grid and grid.get("available"):
        from .site_grid import aligned_orientations, align_building_to_grid
        orientations = aligned_orientations(grid, offsets_deg=orientation_offsets_deg)
        for node in grid.get("grid_nodes", []):
            for ang in orientations:
                bnd = align_building_to_grid(boundary, grid, node, ang)
                placed = _coerce_polygon_2d(bnd)
                if buildable_zone.contains(placed):
                    candidates.append({
                        "centroid_xy": [round(placed.centroid.x, 6), round(placed.centroid.y, 6)],
                        "rotation_degrees": round(ang, 4),
                        "node_xy": node,
                        "aligned": True,
                        "boundary": bnd,
                    })
        return candidates

    min_x, min_y, max_x, max_y = buildable_zone.bounds
    n_steps = 360 // max(1, rotation_step_degrees)

    x_count = max(1, int((max_x - min_x) / grid_step)) + 1
    y_count = max(1, int((max_y - min_y) / grid_step)) + 1

    for rot_idx in range(n_steps):
        rot = rot_idx * rotation_step_degrees
        rotated = affinity.rotate(base_polygon, float(rot), origin=(0.0, 0.0), use_radians=False)
        for xi in range(x_count):
            cx = min_x + xi * grid_step
            for yi in range(y_count):
                cy = min_y + yi * grid_step
                placed = affinity.translate(rotated, xoff=cx, yoff=cy)
                if buildable_zone.contains(placed):
                    candidates.append({
                        "centroid_xy": [round(cx, 6), round(cy, 6)],
                        "rotation_degrees": rot,
                        "boundary": _polygon_to_boundary(placed),
                    })
    return candidates


# ---------------------------------------------------------------------------
# Grid-aligned discrete placement (Phase 3) — exhaustive, deterministic
# ---------------------------------------------------------------------------

def _aligned_default_objectives(
    use: str,
    sun_vectors: list[dict[str, float]] | None,
    sun_weight: float,
    reference_line: list[list[float]] | None,
) -> list[dict[str, Any]]:
    """Use-driven default objective mix for aligned placement.

    Commercial / office / retail / mixed buildings line the street: they get a
    strong ``boundary_proximity`` weight so they hug the chosen frontage.
    Residential leans on view + sun.
    """
    cfgs: list[dict[str, Any]] = [{"name": "unblocked_view", "weight": 1.0}]
    if sun_vectors and sun_weight > 0.0:
        cfgs.append({"name": "sun_avoidance", "weight": float(sun_weight), "sun_vectors": sun_vectors})
    if use.lower() in ("commercial", "office", "retail", "mixed"):
        cfgs.append({
            "name": "boundary_proximity", "weight": 0.9,
            "reference_line": reference_line, "max_distance": 25.0,
        })
    return cfgs


def optimize_aligned_placement(
    *,
    base_boundary: list[list[float]],
    site_boundary: list[list[float]],
    grid: dict[str, Any],
    obstacles: list[list[list[float]]] | None = None,
    objective_configs: list[dict[str, Any]] | None = None,
    use: str = "residential",
    sun_vectors: list[dict[str, float]] | None = None,
    sun_weight: float = 0.0,
    reference_line: list[list[float]] | None = None,
    orientation_offsets_deg: tuple[float, ...] = (),
    site_setbacks: dict[str, Any] | None = None,
    other_buildings: list[list[list[float]]] | None = None,
    min_separation: float = 0.0,
    piece_length: float = 2.0,
    ray_length: float = 100.0,
    saved_option_count: int = 10,
) -> dict[str, Any]:
    """Rank grid-node × aligned-orientation placements by a combined objective.

    This replaces free NSGA-II rotation with an **exhaustive** sweep over the
    discrete aligned candidate set (grid nodes × {parallel, perpendicular}). The
    set is small, so brute-force ranking is exact and deterministic — and it
    structurally guarantees every result is grid-aligned (a building can never
    land at a random angle). ``use`` drives the default objective mix
    (commercial hugs the frontage via ``boundary_proximity``).

    ``other_buildings`` are already-placed footprints to avoid (overlap + an
    optional ``min_separation`` clearance) — pass them to place several buildings
    in sequence (see ``place_buildings_aligned``).
    """
    if not grid or not grid.get("available"):
        return {"optimized": False, "reason": "grid unavailable", "options": []}

    obstacles = list(obstacles or [])
    other_buildings = list(other_buildings or [])
    obj_cfgs = objective_configs or _aligned_default_objectives(
        use, sun_vectors, sun_weight, reference_line)

    site_polygon = _coerce_polygon_2d(site_boundary)
    buildable_zone = (compute_buildable_zone(site_boundary, **site_setbacks)
                      if site_setbacks else site_polygon)

    candidates = sample_valid_placements(
        base_boundary, site_boundary, site_setbacks=site_setbacks,
        grid=grid, orientation_offsets_deg=orientation_offsets_deg,
    )

    other_polys = [_coerce_polygon_2d(b) for b in other_buildings]
    obstacle_polys_base = [_coerce_polygon_2d(o) for o in obstacles]

    scored: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for cand in candidates:
        cand_poly = _coerce_polygon_2d(cand["boundary"])

        # Hard constraints: no overlap, honour separation from placed buildings.
        bad = False
        for other in other_polys:
            if cand_poly.intersects(other) and cand_poly.intersection(other).area > 1e-6:
                bad = True
                break
            if min_separation > 0.0 and cand_poly.distance(other) < min_separation:
                bad = True
                break
        if bad:
            continue

        key = (round(cand["centroid_xy"][0], 2), round(cand["centroid_xy"][1], 2),
               round(cand["rotation_degrees"], 1))
        if key in seen:
            continue
        seen.add(key)

        run_obstacles = obstacles + other_buildings
        run_obstacle_polys = obstacle_polys_base + other_polys
        combined, per_obj = evaluate_combined_score(
            cand["boundary"], obj_cfgs,
            obstacles=run_obstacles, site_polygon=site_polygon,
            candidate_polygon=cand_poly, obstacle_polys=run_obstacle_polys,
            piece_length=piece_length, ray_length=ray_length,
        )
        from .site_grid import alignment_score as _align_score
        scored.append({
            "centroid_xy": cand["centroid_xy"],
            "node_xy": cand.get("node_xy"),
            "orientation_deg": cand["rotation_degrees"],
            "rotation_degrees": cand["rotation_degrees"],
            "combined_score": combined,
            "unblocked_view_score": per_obj.get("unblocked_view", 0.0),
            "sun_exposure_score": (round(1.0 - per_obj["sun_avoidance"], 6)
                                   if "sun_avoidance" in per_obj else None),
            "boundary_proximity_score": per_obj.get("boundary_proximity"),
            "alignment_score": round(_align_score(cand["boundary"], grid), 6),
            "objective_scores": per_obj,
            "fits_within_site": True,
            "aligned": True,
            "boundary": cand["boundary"],
        })

    scored.sort(key=lambda s: -s["combined_score"])
    trimmed = scored[:max(saved_option_count, 1)]
    for rank, sol in enumerate(trimmed, start=1):
        sol["rank"] = rank
        sol["option_id"] = f"aligned_option_{rank:02d}"

    return {
        "optimized": True,
        "algorithm": "exhaustive_grid_aligned",
        "use": use,
        "objective_configs": obj_cfgs,
        "candidate_count": len(candidates),
        "feasible_count": len(scored),
        "alignment_side_index": grid.get("alignment_side_index"),
        "orientations": _orientations_used(grid, orientation_offsets_deg),
        "option_count": len(trimmed),
        "options": trimmed,
    }


def place_buildings_aligned(
    building_specs: list[dict[str, Any]],
    site_boundary: list[list[float]],
    grid: dict[str, Any],
    *,
    external_obstacles: list[list[list[float]]] | None = None,
    sun_vectors: list[dict[str, float]] | None = None,
    sun_weight: float = 0.0,
    reference_line: list[list[float]] | None = None,
    site_setbacks: dict[str, Any] | None = None,
    min_separation: float = 6.0,
    piece_length: float = 2.0,
    ray_length: float = 100.0,
) -> dict[str, Any]:
    """Place two or more buildings on the grid, each aligned and clearing the rest.

    Greedy sequential placement: each building takes its best aligned option
    given the already-placed ones (as obstacles + a ``min_separation`` clearance).
    Each spec is ``{base_boundary, use?, objective_configs?}``.
    """
    external_obstacles = list(external_obstacles or [])
    placed: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []

    for i, spec in enumerate(building_specs):
        res = optimize_aligned_placement(
            base_boundary=spec["base_boundary"],
            site_boundary=site_boundary, grid=grid,
            obstacles=external_obstacles,
            objective_configs=spec.get("objective_configs"),
            use=spec.get("use", "residential"),
            sun_vectors=sun_vectors, sun_weight=sun_weight,
            reference_line=reference_line,
            site_setbacks=site_setbacks,
            other_buildings=[p["boundary"] for p in placed],
            min_separation=min_separation,
            piece_length=piece_length, ray_length=ray_length,
            saved_option_count=5,
        )
        runs.append(res)
        if res.get("options"):
            best = dict(res["options"][0])
            best["building_index"] = i
            best["use"] = spec.get("use", "residential")
            placed.append(best)

    return {
        "placed_count": len(placed),
        "buildings": placed,
        "runs": runs,
    }


def _orientations_used(grid: dict[str, Any], offsets: tuple[float, ...]) -> list[float]:
    from .site_grid import aligned_orientations
    return aligned_orientations(grid, offsets_deg=offsets)


# ---------------------------------------------------------------------------
# Step 2: Evaluate and rank by view score
# ---------------------------------------------------------------------------

def rank_placements_by_view(
    placements: list[dict[str, Any]],
    obstacles: list[list[list[float]]],
    *,
    piece_length: float = 2.0,
    ray_length: float = 100.0,
) -> list[dict[str, Any]]:
    """Evaluate perpendicular-ray view score for each valid placement and rank descending."""
    results: list[dict[str, Any]] = []
    for p in placements:
        r = evaluate_building_views(p["boundary"], obstacles,
                                    piece_length=piece_length, ray_length=ray_length,
                                    return_ray_detail=False)
        results.append({**p, "view_score": r["view_score"],
                        "total_unblocked_rays": r["total_unblocked_rays"],
                        "total_rays": r["total_rays"]})
    results.sort(key=lambda x: -x["view_score"])
    return results


# ---------------------------------------------------------------------------
# NSGA-II: single-building optimizer
# ---------------------------------------------------------------------------

def optimize_view_placement(
    *,
    boundary: list[list[float]],
    site_boundary: list[list[float]],
    obstacles: list[list[list[float]]],
    # Objective config — explicit list takes precedence over legacy params
    objective_configs: list[dict[str, Any]] | None = None,
    attractors: list[dict[str, Any]] | None = None,
    attractor_weight: float = 0.3,
    # Phase 1 sun avoidance: pass sun_vectors + a sun_weight to add the objective.
    sun_vectors: list[dict[str, float]] | None = None,
    sun_weight: float = 0.0,
    # Wing-parametric shape morphing
    optimize_shape: bool = False,
    building_type: str = "L",
    # Setback options (passed to compute_buildable_zone)
    site_setbacks: dict[str, Any] | None = None,
    # Ray / geometry params
    piece_length: float = 2.0,
    ray_length: float = 100.0,
    rotation_step_degrees: int = 10,
    population_size: int = 50,
    generation_count: int = 100,
    random_seed: int = 7,
    saved_option_count: int = 10,
) -> dict[str, Any]:
    """
    Single-building NSGA-II view placement.

    With attractors (or objective_configs with attractor_view):
        F[0] = -unblocked_score   F[1] = -attractor_score   (true 2-obj Pareto)
    Without:
        F[0] = -view_score        F[1] = -clearance_from_site

    Hard constraint: G[0] = outside_area ≤ 0.

    Wing shape (optimize_shape=True):
        Adds [building_depth, shape_ratio, end_rot_i…] variables.
        area is preserved; wing thickness preserved; end arms can bend ±45°.
    """
    _ensure_pymoo_available()
    _obj_cfgs = objective_configs or _default_objective_configs(
        attractors, attractor_weight, sun_vectors, sun_weight)
    _has_attractor = any(c["name"] == "attractor_view" for c in _obj_cfgs)
    _sun_cfg = next((c for c in _obj_cfgs if c["name"] == "sun_avoidance"), None)
    _has_sun = _sun_cfg is not None and not _has_attractor

    base_polygon = _coerce_polygon_2d(boundary)
    site_polygon = _coerce_polygon_2d(site_boundary)
    buildable_zone = (compute_buildable_zone(site_boundary, **site_setbacks)
                      if site_setbacks else site_polygon)
    min_x, min_y, max_x, max_y = buildable_zone.bounds
    n_steps = 360 // max(1, rotation_step_degrees)
    target_area = base_polygon.area

    # Placement variables: [cx, cy, rot_idx]
    place_lb = [min_x, min_y, 0.0]
    place_ub = [max_x, max_y, float(n_steps) - 1e-9]

    # Shape variables
    if optimize_shape:
        spec = shape_variable_spec(building_type, target_area)
        shape_lb = spec["lower"]
        shape_ub = spec["upper"]
        leaf_indices = spec["leaf_wing_indices"]
    else:
        shape_lb = shape_ub = []
        leaf_indices = []

    lower_bounds = place_lb + shape_lb
    upper_bounds = place_ub + shape_ub
    n_var = len(lower_bounds)
    obstacle_polys = [_coerce_polygon_2d(obs) for obs in obstacles]

    class _ViewProblem(ElementwiseProblem):
        def __init__(self) -> None:
            super().__init__(n_var=n_var, n_obj=2, n_ieq_constr=1,
                             xl=lower_bounds, xu=upper_bounds)

        def _evaluate(self, x, out, *args, **kwargs) -> None:  # type: ignore[override]
            del args, kwargs
            cx, cy = float(x[0]), float(x[1])
            rot = int(x[2]) * rotation_step_degrees

            if optimize_shape:
                shape_vars = [float(v) for v in x[3:]]
                base = apply_shape_variables(building_type, target_area, shape_vars, leaf_indices)
            else:
                base = base_polygon

            candidate = _transform_polygon(base, (cx, cy), rot)
            outside_area = max(candidate.area - candidate.intersection(buildable_zone).area, 0.0)
            bnd = _polygon_to_boundary(candidate)

            combined, _ = evaluate_combined_score(
                bnd, _obj_cfgs,
                obstacles=obstacles, site_polygon=site_polygon,
                candidate_polygon=candidate, obstacle_polys=obstacle_polys,
                piece_length=piece_length, ray_length=ray_length,
            )

            if _has_attractor:
                # Get individual objectives for 2-dim Pareto
                u = _obj_unblocked_view(bnd, obstacles=obstacles,
                                        piece_length=piece_length, ray_length=ray_length)
                attr_cfg = next(c for c in _obj_cfgs if c["name"] == "attractor_view")
                a = _obj_attractor_view(bnd, obstacles=obstacles, piece_length=piece_length,
                                        attractors=attr_cfg.get("attractors"))
                out["F"] = [-u, -a]
            elif _has_sun:
                # True 2-objective view-vs-sun Pareto front (Phase 1).
                u = _obj_unblocked_view(bnd, obstacles=obstacles,
                                        piece_length=piece_length, ray_length=ray_length)
                s = _obj_sun_avoidance(bnd, obstacles=obstacles, piece_length=piece_length,
                                       sun_vectors=_sun_cfg.get("sun_vectors"))
                out["F"] = [-u, -s]
            else:
                clearance = (site_polygon.boundary.distance(candidate)
                             if outside_area <= 1e-6 else 0.0)
                out["F"] = [-combined, -clearance]

            out["G"] = [outside_area - 1e-6]

    result = pymoo_minimize(
        _ViewProblem(),
        NSGA2(pop_size=max(population_size, 10), eliminate_duplicates=True),
        ("n_gen", max(generation_count, 1)),
        seed=random_seed, verbose=False,
    )

    solutions = _collect_single_building_solutions(
        result=result,
        base_polygon=base_polygon,
        site_polygon=site_polygon,
        rotation_step_degrees=rotation_step_degrees,
        optimize_shape=optimize_shape,
        building_type=building_type,
        target_area=target_area,
        leaf_indices=leaf_indices,
        obj_cfgs=_obj_cfgs,
        obstacles=obstacles,
        obstacle_polys=obstacle_polys,
        piece_length=piece_length,
        ray_length=ray_length,
        has_attractor=_has_attractor,
        limit=max(saved_option_count, 1),
    )

    return {
        "optimized": True,
        "algorithm": "NSGA2",
        "objective_configs": _obj_cfgs,
        "optimize_shape": optimize_shape,
        "building_type": building_type if optimize_shape else None,
        "rotation_step_degrees": rotation_step_degrees,
        "population_size": population_size,
        "generation_count": generation_count,
        "random_seed": random_seed,
        "pareto_solution_count": len(solutions),
        "pareto_solutions": solutions,
    }


# ---------------------------------------------------------------------------
# NSGA-II: two-building optimizer
# ---------------------------------------------------------------------------

def optimize_two_building_placement(
    *,
    boundary_1: list[list[float]],
    boundary_2: list[list[float]],
    site_boundary: list[list[float]],
    external_obstacles: list[list[list[float]]],
    # Objective config
    objective_configs: list[dict[str, Any]] | None = None,
    attractors: list[dict[str, Any]] | None = None,
    attractor_weight: float = 0.3,
    # Phase 1 sun avoidance: each building shades the other (mutual shading) via
    # the existing other-building-as-obstacle pattern.
    sun_vectors: list[dict[str, float]] | None = None,
    sun_weight: float = 0.0,
    # Wing-parametric shape morphing (applied per building independently)
    optimize_shape: bool = False,
    building_type_1: str = "L",
    building_type_2: str = "L",
    # Setback and clearance constraints
    site_setbacks: dict[str, Any] | None = None,
    min_building_separation: float = 0.0,
    # Ray / geometry params
    piece_length: float = 2.0,
    ray_length: float = 100.0,
    rotation_step_degrees: int = 10,
    population_size: int = 60,
    generation_count: int = 150,
    random_seed: int = 7,
    saved_option_count: int = 10,
) -> dict[str, Any]:
    """
    Joint two-building NSGA-II placement.

    Combined score per building = weighted average over objective_configs.
    F[0] = -combined_1    F[1] = -combined_2   (Pareto between buildings)

    Hard constraints (G ≤ 0):
        G[0] = outside_area_1 ≤ 0
        G[1] = outside_area_2 ≤ 0
        G[2] = overlap ≤ 0

    Wing shape (optimize_shape=True):
        Adds [depth1, ratio1, end_rot1…, depth2, ratio2, end_rot2…] variables.
        Type can differ per building (building_type_1, building_type_2).
    """
    _ensure_pymoo_available()
    _obj_cfgs = objective_configs or _default_objective_configs(
        attractors, attractor_weight, sun_vectors, sun_weight)

    base_poly1 = _coerce_polygon_2d(boundary_1)
    base_poly2 = _coerce_polygon_2d(boundary_2)
    site_polygon = _coerce_polygon_2d(site_boundary)
    buildable_zone = (compute_buildable_zone(site_boundary, **site_setbacks)
                      if site_setbacks else site_polygon)
    min_x, min_y, max_x, max_y = buildable_zone.bounds
    n_steps = 360 // max(1, rotation_step_degrees)
    area1, area2 = base_poly1.area, base_poly2.area
    _min_sep = float(min_building_separation)

    place_lb = [min_x, min_y, 0.0]
    place_ub = [max_x, max_y, float(n_steps) - 1e-9]

    if optimize_shape:
        spec1 = shape_variable_spec(building_type_1, area1)
        spec2 = shape_variable_spec(building_type_2, area2)
        leaf1, leaf2 = spec1["leaf_wing_indices"], spec2["leaf_wing_indices"]
        shape_lb1, shape_ub1 = spec1["lower"], spec1["upper"]
        shape_lb2, shape_ub2 = spec2["lower"], spec2["upper"]
    else:
        leaf1 = leaf2 = []
        shape_lb1 = shape_ub1 = shape_lb2 = shape_ub2 = []

    lower_bounds = place_lb + shape_lb1 + place_lb + shape_lb2
    upper_bounds = place_ub + shape_ub1 + place_ub + shape_ub2
    n_place = 3
    n_shape1 = len(shape_lb1)
    n_var = len(lower_bounds)
    obstacle_polys = [_coerce_polygon_2d(obs) for obs in external_obstacles]

    _n_constr = 4 if _min_sep > 0.0 else 3

    class _TwoBldProblem(ElementwiseProblem):
        def __init__(self) -> None:
            super().__init__(n_var=n_var, n_obj=2, n_ieq_constr=_n_constr,
                             xl=lower_bounds, xu=upper_bounds)

        def _evaluate(self, x, out, *args, **kwargs) -> None:  # type: ignore[override]
            del args, kwargs
            i1 = 0
            cx1, cy1 = float(x[i1]), float(x[i1+1])
            rot1 = int(x[i1+2]) * rotation_step_degrees
            i2 = n_place + n_shape1
            cx2, cy2 = float(x[i2]), float(x[i2+1])
            rot2 = int(x[i2+2]) * rotation_step_degrees

            if optimize_shape:
                sv1 = [float(v) for v in x[n_place: n_place + n_shape1]]
                sv2 = [float(v) for v in x[i2+3:]]
                poly1 = apply_shape_variables(building_type_1, area1, sv1, leaf1)
                poly2 = apply_shape_variables(building_type_2, area2, sv2, leaf2)
            else:
                poly1, poly2 = base_poly1, base_poly2

            bld1 = _transform_polygon(poly1, (cx1, cy1), rot1)
            bld2 = _transform_polygon(poly2, (cx2, cy2), rot2)
            bnd1 = _polygon_to_boundary(bld1)
            bnd2 = _polygon_to_boundary(bld2)

            oa1 = max(bld1.area - bld1.intersection(buildable_zone).area, 0.0)
            oa2 = max(bld2.area - bld2.intersection(buildable_zone).area, 0.0)
            overlap = bld1.intersection(bld2).area

            obs1 = external_obstacles + [bnd2]
            obs2 = external_obstacles + [bnd1]
            obs_polys1 = obstacle_polys + [bld2]
            obs_polys2 = obstacle_polys + [bld1]

            c1, _ = evaluate_combined_score(
                bnd1, _obj_cfgs, obstacles=obs1, site_polygon=site_polygon,
                candidate_polygon=bld1, obstacle_polys=obs_polys1,
                piece_length=piece_length, ray_length=ray_length,
            )
            c2, _ = evaluate_combined_score(
                bnd2, _obj_cfgs, obstacles=obs2, site_polygon=site_polygon,
                candidate_polygon=bld2, obstacle_polys=obs_polys2,
                piece_length=piece_length, ray_length=ray_length,
            )

            out["F"] = [-c1, -c2]
            g = [oa1 - 1e-6, oa2 - 1e-6, overlap - 1e-6]
            if _min_sep > 0.0:
                g.append(clearance_constraint_value(bld1, bld2, _min_sep))
            out["G"] = g

    result = pymoo_minimize(
        _TwoBldProblem(),
        NSGA2(pop_size=max(population_size, 10), eliminate_duplicates=True),
        ("n_gen", max(generation_count, 1)),
        seed=random_seed, verbose=False,
    )

    solutions = _collect_two_building_solutions(
        result=result,
        base_poly1=base_poly1, base_poly2=base_poly2,
        site_polygon=site_polygon,
        rotation_step_degrees=rotation_step_degrees,
        optimize_shape=optimize_shape,
        building_type_1=building_type_1, building_type_2=building_type_2,
        area1=area1, area2=area2,
        leaf1=leaf1, leaf2=leaf2,
        n_place=n_place, n_shape1=n_shape1,
        obj_cfgs=_obj_cfgs,
        external_obstacles=external_obstacles,
        obstacle_polys=obstacle_polys,
        piece_length=piece_length, ray_length=ray_length,
        limit=max(saved_option_count, 1),
    )

    return {
        "optimized": True,
        "algorithm": "NSGA2",
        "objective_configs": _obj_cfgs,
        "optimize_shape": optimize_shape,
        "site_setbacks_used": site_setbacks is not None,
        "min_building_separation_m": _min_sep,
        "rotation_step_degrees": rotation_step_degrees,
        "population_size": population_size,
        "generation_count": generation_count,
        "random_seed": random_seed,
        "pareto_solution_count": len(solutions),
        "best_avg_combined_score": (
            (solutions[0]["building_1"]["combined_score"] + solutions[0]["building_2"]["combined_score"]) / 2
            if solutions else 0.0
        ),
        "pareto_solutions": solutions,
    }


# ---------------------------------------------------------------------------
# Internal: result collection
# ---------------------------------------------------------------------------

def _collect_single_building_solutions(
    *,
    result: Any,
    base_polygon: Polygon,
    site_polygon: Polygon,
    rotation_step_degrees: int,
    optimize_shape: bool,
    building_type: str,
    target_area: float,
    leaf_indices: list[int],
    obj_cfgs: list[dict[str, Any]],
    obstacles: list[list[list[float]]],
    obstacle_polys: list[Polygon],
    piece_length: float,
    ray_length: float,
    has_attractor: bool,
    limit: int,
) -> list[dict[str, Any]]:
    if result is None or result.X is None or result.F is None:
        return []

    X, F = _to_2d(result.X), _to_2d(result.F)
    solutions: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    n_shape = shape_variable_spec(building_type, target_area)["n_shape_vars"] if optimize_shape else 0

    for x_row, f_row in zip(X, F):
        cx, cy = float(x_row[0]), float(x_row[1])
        rot = int(x_row[2]) * rotation_step_degrees
        shape_key = tuple(round(float(v), 3) for v in x_row[3:3+n_shape]) if optimize_shape else ()

        key = (round(cx, 2), round(cy, 2), rot) + shape_key
        if key in seen:
            continue
        seen.add(key)

        if optimize_shape:
            shape_vars = [float(v) for v in x_row[3:3+n_shape]]
            poly = apply_shape_variables(building_type, target_area, shape_vars, leaf_indices)
        else:
            poly = base_polygon

        candidate = _transform_polygon(poly, (cx, cy), rot)
        outside_area = max(candidate.area - candidate.intersection(site_polygon).area, 0.0)
        if outside_area > 0.5:
            continue

        bnd = _polygon_to_boundary(candidate)
        combined, per_obj = evaluate_combined_score(
            bnd, obj_cfgs, obstacles=obstacles, site_polygon=site_polygon,
            candidate_polygon=candidate, obstacle_polys=obstacle_polys,
            piece_length=piece_length, ray_length=ray_length,
        )

        depth = round(float(x_row[3]), 3) if optimize_shape else None
        ratio = round(float(x_row[4]), 3) if optimize_shape and n_shape > 1 else None
        end_rots = {leaf_indices[k]: round(float(x_row[5+k]), 2)
                    for k in range(len(leaf_indices)) if (5+k) < len(x_row)} if optimize_shape else {}

        solutions.append({
            "centroid_xy": [round(cx, 6), round(cy, 6)],
            "rotation_degrees": rot,
            "building_depth": depth,
            "shape_ratio": ratio,
            "end_wing_rotations": end_rots,
            "combined_score": combined,
            "unblocked_view_score": per_obj.get("unblocked_view", 0.0),
            "attractor_view_score": per_obj.get("attractor_view", 0.0),
            "sun_avoidance_score": per_obj.get("sun_avoidance"),
            "sun_exposure_score": (round(1.0 - per_obj["sun_avoidance"], 6)
                                   if "sun_avoidance" in per_obj else None),
            "objective_scores": per_obj,
            "outside_area_sqm": round(outside_area, 6),
            "fits_within_site": True,
            "boundary": bnd,
        })

    solutions.sort(key=lambda s: -s["combined_score"])
    trimmed = solutions[:limit]
    for rank, sol in enumerate(trimmed, start=1):
        sol["rank"] = rank
        sol["option_id"] = f"view_option_{rank:02d}"
    return trimmed


def _collect_two_building_solutions(
    *,
    result: Any,
    base_poly1: Polygon, base_poly2: Polygon,
    site_polygon: Polygon,
    rotation_step_degrees: int,
    optimize_shape: bool,
    building_type_1: str, building_type_2: str,
    area1: float, area2: float,
    leaf1: list[int], leaf2: list[int],
    n_place: int, n_shape1: int,
    obj_cfgs: list[dict[str, Any]],
    external_obstacles: list[list[list[float]]],
    obstacle_polys: list[Polygon],
    piece_length: float, ray_length: float,
    limit: int,
) -> list[dict[str, Any]]:
    if result is None or result.X is None or result.F is None:
        return []

    X, F = _to_2d(result.X), _to_2d(result.F)
    solutions: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    n_shape2 = (shape_variable_spec(building_type_2, area2)["n_shape_vars"]
                if optimize_shape else 0)
    i2_start = n_place + n_shape1

    for x_row, _ in zip(X, F):
        cx1, cy1 = float(x_row[0]), float(x_row[1])
        rot1 = int(x_row[2]) * rotation_step_degrees
        cx2, cy2 = float(x_row[i2_start]), float(x_row[i2_start+1])
        rot2 = int(x_row[i2_start+2]) * rotation_step_degrees

        key = (round(cx1,2), round(cy1,2), rot1, round(cx2,2), round(cy2,2), rot2)
        if key in seen:
            continue
        seen.add(key)

        if optimize_shape:
            sv1 = [float(v) for v in x_row[n_place: n_place+n_shape1]]
            sv2 = [float(v) for v in x_row[i2_start+3: i2_start+3+n_shape2]]
            poly1 = apply_shape_variables(building_type_1, area1, sv1, leaf1)
            poly2 = apply_shape_variables(building_type_2, area2, sv2, leaf2)
        else:
            poly1, poly2 = base_poly1, base_poly2

        bld1 = _transform_polygon(poly1, (cx1, cy1), rot1)
        bld2 = _transform_polygon(poly2, (cx2, cy2), rot2)
        bnd1, bnd2 = _polygon_to_boundary(bld1), _polygon_to_boundary(bld2)

        oa1 = max(bld1.area - bld1.intersection(site_polygon).area, 0.0)
        oa2 = max(bld2.area - bld2.intersection(site_polygon).area, 0.0)
        if oa1 > 0.5 or oa2 > 0.5:
            continue
        overlap = bld1.intersection(bld2).area

        obs1 = external_obstacles + [bnd2]
        obs2 = external_obstacles + [bnd1]

        c1, per1 = evaluate_combined_score(
            bnd1, obj_cfgs, obstacles=obs1, site_polygon=site_polygon,
            candidate_polygon=bld1, obstacle_polys=obstacle_polys + [bld2],
            piece_length=piece_length, ray_length=ray_length,
        )
        c2, per2 = evaluate_combined_score(
            bnd2, obj_cfgs, obstacles=obs2, site_polygon=site_polygon,
            candidate_polygon=bld2, obstacle_polys=obstacle_polys + [bld1],
            piece_length=piece_length, ray_length=ray_length,
        )

        actual_clearance = round(bld1.distance(bld2), 4)
        solutions.append({
            "avg_combined_score": round((c1 + c2) / 2, 6),
            "overlap_area_sqm": round(overlap, 6),
            "clearance_between_buildings_m": actual_clearance,
            "building_1": {
                "centroid_xy": [round(cx1, 6), round(cy1, 6)],
                "rotation_degrees": rot1,
                "combined_score": c1,
                "unblocked_view_score": per1.get("unblocked_view", 0.0),
                "attractor_view_score": per1.get("attractor_view", 0.0),
                "sun_avoidance_score": per1.get("sun_avoidance"),
                "sun_exposure_score": (round(1.0 - per1["sun_avoidance"], 6)
                                       if "sun_avoidance" in per1 else None),
                "objective_scores": per1,
                "outside_area_sqm": round(oa1, 6),
                "fits_within_site": True,
                "boundary": bnd1,
            },
            "building_2": {
                "centroid_xy": [round(cx2, 6), round(cy2, 6)],
                "rotation_degrees": rot2,
                "combined_score": c2,
                "unblocked_view_score": per2.get("unblocked_view", 0.0),
                "attractor_view_score": per2.get("attractor_view", 0.0),
                "sun_avoidance_score": per2.get("sun_avoidance"),
                "sun_exposure_score": (round(1.0 - per2["sun_avoidance"], 6)
                                       if "sun_avoidance" in per2 else None),
                "objective_scores": per2,
                "outside_area_sqm": round(oa2, 6),
                "fits_within_site": True,
                "boundary": bnd2,
            },
        })

    solutions.sort(key=lambda s: (-s["avg_combined_score"], s["overlap_area_sqm"]))
    trimmed = solutions[:limit]
    for rank, sol in enumerate(trimmed, start=1):
        sol["rank"] = rank
        sol["option_id"] = f"two_bld_option_{rank:02d}"
    return trimmed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_2d(arr: Any) -> Any:
    if arr.ndim == 1:
        return arr.reshape(1, -1)
    return arr


def _transform_polygon(
    polygon: Polygon,
    centroid_xy: tuple[float, float],
    rotation_degrees: int | float,
) -> Polygon:
    rotated = affinity.rotate(polygon, float(rotation_degrees),
                              origin=(0.0, 0.0), use_radians=False)
    return affinity.translate(rotated, xoff=centroid_xy[0], yoff=centroid_xy[1])


def _polygon_to_boundary(polygon: Polygon) -> list[list[float]]:
    return [[round(float(x), 6), round(float(y), 6), 0.0]
            for x, y in polygon.exterior.coords]


def _ensure_pymoo_available() -> None:
    if _PYMOO_IMPORT_ERROR is not None:
        raise RuntimeError("pymoo is required") from _PYMOO_IMPORT_ERROR
