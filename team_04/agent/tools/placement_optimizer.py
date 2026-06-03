from __future__ import annotations

from typing import Any

from shapely import affinity
from shapely.geometry import Point, Polygon

_PYMOO_IMPORT_ERROR: Exception | None = None

try:
    from pymoo.algorithms.soo.nonconvex.ga import GA
    from pymoo.core.problem import ElementwiseProblem
    from pymoo.optimize import minimize
except Exception as exc:  # pragma: no cover - exercised through tool calls
    GA = None
    ElementwiseProblem = None
    minimize = None
    _PYMOO_IMPORT_ERROR = exc


def optimize_boundary_placement(
    *,
    boundary: list[list[float]] | list[tuple[float, float]],
    site_boundary: list[list[float]] | list[tuple[float, float]],
    fixed_rotation_degrees: float | None = None,
    rotation_limit_degrees: float = 180.0,
    target_location_xy: tuple[float, float] | None = None,
    clearance_target: float = 0.0,
    population_size: int = 40,
    generation_count: int = 60,
    random_seed: int = 7,
) -> dict[str, Any]:
    _ensure_pymoo_available()
    base_polygon = _coerce_polygon(boundary)
    site_polygon = _coerce_polygon(site_boundary)
    target_point = Point(target_location_xy) if target_location_xy is not None else None
    min_x, min_y, max_x, max_y = site_polygon.bounds

    if fixed_rotation_degrees is None and rotation_limit_degrees > 0:
        lower_bounds = [min_x, min_y, -abs(rotation_limit_degrees)]
        upper_bounds = [max_x, max_y, abs(rotation_limit_degrees)]
    else:
        lower_bounds = [min_x, min_y]
        upper_bounds = [max_x, max_y]

    class PlacementProblem(ElementwiseProblem):
        def __init__(self) -> None:
            super().__init__(n_var=len(lower_bounds), n_obj=1, xl=lower_bounds, xu=upper_bounds)

        def _evaluate(self, x, out, *args, **kwargs) -> None:
            del args
            del kwargs
            if len(x) == 3:
                candidate = _transform_polygon(base_polygon, centroid_xy=(float(x[0]), float(x[1])), rotation_degrees=float(x[2]))
            else:
                candidate = _transform_polygon(
                    base_polygon,
                    centroid_xy=(float(x[0]), float(x[1])),
                    rotation_degrees=fixed_rotation_degrees or 0.0,
                )
            summary = _summarize_candidate(
                candidate_polygon=candidate,
                site_polygon=site_polygon,
                clearance_target=clearance_target,
                target_point=target_point,
            )
            out["F"] = summary["objective"]

    algorithm = GA(pop_size=max(population_size, 10), eliminate_duplicates=True)
    result = minimize(
        PlacementProblem(),
        algorithm,
        ("n_gen", max(generation_count, 1)),
        seed=random_seed,
        verbose=False,
    )

    solution = result.X
    if solution is None:
        centroid_xy = (site_polygon.centroid.x, site_polygon.centroid.y)
        rotation_degrees = fixed_rotation_degrees or 0.0
    elif len(solution) == 3:
        centroid_xy = (float(solution[0]), float(solution[1]))
        rotation_degrees = float(solution[2])
    else:
        centroid_xy = (float(solution[0]), float(solution[1]))
        rotation_degrees = fixed_rotation_degrees or 0.0

    placed_polygon = _transform_polygon(base_polygon, centroid_xy=centroid_xy, rotation_degrees=rotation_degrees)
    summary = _summarize_candidate(
        candidate_polygon=placed_polygon,
        site_polygon=site_polygon,
        clearance_target=clearance_target,
        target_point=target_point,
    )
    return {
        "optimized": True,
        "centroid_xy": [round(centroid_xy[0], 6), round(centroid_xy[1], 6)],
        "rotation_degrees": round(rotation_degrees, 6),
        "objective": round(summary["objective"], 6),
        "outside_area_sqm": round(summary["outside_area_sqm"], 6),
        "clearance_m": round(summary["clearance_m"], 6),
        "fits_within_site_boundary": summary["fits_within_site_boundary"],
        "population_size": population_size,
        "generation_count": generation_count,
        "random_seed": random_seed,
        "target_location_xy": list(target_location_xy) if target_location_xy is not None else [],
    }


def evaluate_boundary_fit(
    *,
    boundary: list[list[float]] | list[tuple[float, float]],
    site_boundary: list[list[float]] | list[tuple[float, float]],
    clearance_target: float = 0.0,
) -> dict[str, Any]:
    candidate_polygon = _coerce_polygon(boundary)
    site_polygon = _coerce_polygon(site_boundary)
    summary = _summarize_candidate(
        candidate_polygon=candidate_polygon,
        site_polygon=site_polygon,
        clearance_target=clearance_target,
        target_point=None,
    )
    return {
        "outside_area_sqm": round(summary["outside_area_sqm"], 6),
        "clearance_m": round(summary["clearance_m"], 6),
        "fits_within_site_boundary": summary["fits_within_site_boundary"],
        "clearance_target_m": round(clearance_target, 6),
    }


def _transform_polygon(
    polygon: Polygon,
    *,
    centroid_xy: tuple[float, float],
    rotation_degrees: float,
) -> Polygon:
    rotated = affinity.rotate(polygon, rotation_degrees, origin=(0.0, 0.0), use_radians=False)
    return affinity.translate(rotated, xoff=centroid_xy[0], yoff=centroid_xy[1])


def _summarize_candidate(
    *,
    candidate_polygon: Polygon,
    site_polygon: Polygon,
    clearance_target: float,
    target_point: Point | None,
) -> dict[str, Any]:
    outside_area = max(candidate_polygon.area - candidate_polygon.intersection(site_polygon).area, 0.0)
    clearance = site_polygon.boundary.distance(candidate_polygon) if outside_area <= 1e-6 else 0.0
    target_distance = candidate_polygon.centroid.distance(target_point) if target_point is not None else 0.0
    objective = (outside_area * 1000000.0) + (max(clearance_target - clearance, 0.0) * 10000.0) + (target_distance * 0.25) - clearance
    return {
        "outside_area_sqm": outside_area,
        "clearance_m": clearance,
        "fits_within_site_boundary": outside_area <= 1e-6 and clearance >= max(clearance_target - 1e-6, 0.0),
        "objective": objective,
    }


def _coerce_polygon(boundary: list[list[float]] | list[tuple[float, float]]) -> Polygon:
    points = [(float(point[0]), float(point[1])) for point in boundary]
    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if not isinstance(polygon, Polygon) or polygon.area <= 0:
        raise ValueError("boundary must define a valid polygon")
    return polygon


def _ensure_pymoo_available() -> None:
    if _PYMOO_IMPORT_ERROR is not None:
        raise RuntimeError("pymoo is required for Team 04 placement optimization") from _PYMOO_IMPORT_ERROR
