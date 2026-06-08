"""View ray evaluation — boundary test points and outward ray casting."""
from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient as _orient_polygon
from shapely.ops import unary_union


def evaluate_building_views(
    building_boundary: list[list[float]],
    obstacles: list[list[list[float]]],
    *,
    piece_length: float = 2.0,
    ray_count: int = 1,
    ray_spread_degrees: float = 0.0,
    ray_length: float = 100.0,
    return_ray_detail: bool = True,
) -> dict[str, Any]:
    """
    Evaluate view quality from a building boundary against obstacle polygons.

    The building boundary is divided into test points spaced ~piece_length apart.
    From each test point one ray is cast perpendicular to the boundary (outward
    normal). Rays blocked by any obstacle reduce the score.

    ``ray_count=1`` (default) casts a single perpendicular ray per test point.
    Higher values spread rays in a fan of ``ray_spread_degrees`` width.

    Args:
        building_boundary: Closed polygon [[x, y, z|2], ...].
        obstacles: Obstacle polygons blocking views (external buildings, other placed buildings).
        piece_length: Target spacing between test points on the boundary (m).
        ray_count: Rays per test point (1 = perpendicular only).
        ray_spread_degrees: Total angular width of the ray fan when ray_count > 1.
        ray_length: Max ray reach (m).
        return_ray_detail: Include per-ray dicts. Set False for optimization speed.

    Returns dict with:
        view_score (0–1), total_unblocked_rays, total_rays,
        test_point_count, per_test_point (list of point results).
    """
    obstacle_polys = [_coerce_polygon_2d(obs) for obs in obstacles]
    # Pre-build union for fast intersection tests when detail is not needed
    obstacle_union = unary_union(obstacle_polys) if obstacle_polys else None

    test_pts = divide_boundary_into_test_points(building_boundary, piece_length=piece_length)

    total_unblocked = 0
    total_rays = 0
    per_point: list[dict[str, Any]] = []

    for tp in test_pts:
        result = _cast_rays_from_point(
            point=tp["point"],
            outward_normal=tp["outward_normal"],
            obstacle_polys=obstacle_polys,
            obstacle_union=obstacle_union,
            ray_count=ray_count,
            ray_spread_degrees=ray_spread_degrees,
            ray_length=ray_length,
            return_ray_detail=return_ray_detail,
        )
        total_unblocked += result["unblocked_count"]
        total_rays += result["total_count"]

        entry: dict[str, Any] = {
            "point": tp["point"],
            "outward_normal": tp["outward_normal"],
            "segment_index": tp["segment_index"],
            "piece_index": tp["piece_index"],
            "unblocked_count": result["unblocked_count"],
            "total_count": result["total_count"],
        }
        if return_ray_detail:
            entry["rays"] = result["rays"]
        per_point.append(entry)

    view_score = total_unblocked / total_rays if total_rays > 0 else 0.0

    return {
        "view_score": round(view_score, 6),
        "total_unblocked_rays": total_unblocked,
        "total_rays": total_rays,
        "test_point_count": len(test_pts),
        "piece_length_m": piece_length,
        "ray_count_per_point": ray_count,
        "ray_spread_degrees": ray_spread_degrees,
        "ray_length_m": ray_length,
        "per_test_point": per_point,
    }


def divide_boundary_into_test_points(
    boundary: list[list[float]],
    piece_length: float = 2.0,
) -> list[dict[str, Any]]:
    """
    Divide each boundary segment into equal-sized pieces and return midpoint test points.

    Each piece gets a test point at its midpoint. The number of pieces per segment
    is round(segment_length / piece_length), so actual spacing tracks piece_length.
    Each test point carries the outward-facing normal of its parent segment.

    The polygon is re-oriented to CCW (positive signed area) so outward normals
    computed as the right-perpendicular of each directed edge are correct.
    """
    xy_pts = [(float(p[0]), float(p[1])) for p in boundary]
    polygon = _orient_polygon(Polygon(xy_pts), sign=1.0)  # ensure CCW
    coords = list(polygon.exterior.coords)[:-1]  # drop repeated closing vertex
    n = len(coords)

    test_points: list[dict[str, Any]] = []

    for i in range(n):
        ax, ay = coords[i]
        bx, by = coords[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        seg_len = math.hypot(dx, dy)
        if seg_len < 1e-9:
            continue

        # Outward normal for CCW polygon: right-perpendicular of edge direction (dx, dy)
        # right-perp = (dy, -dx) / seg_len
        nx, ny = dy / seg_len, -dx / seg_len

        n_pieces = max(1, round(seg_len / piece_length))
        for j in range(n_pieces):
            t = (j + 0.5) / n_pieces  # midpoint of piece along segment
            test_points.append({
                "point": [round(ax + dx * t, 6), round(ay + dy * t, 6)],
                "outward_normal": [round(nx, 6), round(ny, 6)],
                "segment_index": i,
                "piece_index": j,
                "n_pieces_in_segment": n_pieces,
            })

    return test_points


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cast_rays_from_point(
    *,
    point: list[float],
    outward_normal: list[float],
    obstacle_polys: list[Polygon],
    obstacle_union: Any,
    ray_count: int,
    ray_spread_degrees: float,
    ray_length: float,
    return_ray_detail: bool,
    offset_distance: float = 0.05,
) -> dict[str, Any]:
    """Cast a fan of rays from a boundary test point outward."""
    nx, ny = float(outward_normal[0]), float(outward_normal[1])
    normal_angle = math.atan2(ny, nx)
    half_spread = math.radians(ray_spread_degrees / 2.0)

    # Offset start point slightly outward to avoid boundary self-intersection
    ox = float(point[0]) + nx * offset_distance
    oy = float(point[1]) + ny * offset_distance

    unblocked = 0
    ray_results: list[dict[str, Any]] = []

    for k in range(ray_count):
        if ray_count == 1:
            angle = normal_angle
        else:
            t = k / (ray_count - 1)
            angle = normal_angle - half_spread + t * 2.0 * half_spread

        rdx = math.cos(angle) * ray_length
        rdy = math.sin(angle) * ray_length
        ray = LineString([(ox, oy), (ox + rdx, oy + rdy)])

        if return_ray_detail:
            # Per-obstacle detection for detailed output
            blocked = False
            blocked_by: int | None = None
            for obs_idx, obs_poly in enumerate(obstacle_polys):
                if ray.intersects(obs_poly):
                    blocked = True
                    blocked_by = obs_idx
                    break
            ray_results.append({
                "angle_degrees": round(math.degrees(angle), 2),
                "blocked": blocked,
                "blocked_by_obstacle_index": blocked_by,
            })
        else:
            # Fast path: single union check
            blocked = obstacle_union is not None and ray.intersects(obstacle_union)

        if not blocked:
            unblocked += 1

    return {
        "unblocked_count": unblocked,
        "total_count": ray_count,
        "rays": ray_results,
    }


def evaluate_attractor_views(
    building_boundary: list[list[float]],
    attractors: list[dict[str, Any]],
    obstacles: list[list[list[float]]],
    *,
    piece_length: float = 2.0,
    return_ray_detail: bool = True,
) -> dict[str, Any]:
    """
    Evaluate sight lines from building boundary test points toward attractor geometry.

    For each test point, for each attractor, a ray is cast toward the nearest point
    on the attractor.  The ray is "unblocked" if it reaches the attractor without
    intersecting any obstacle polygon.

    attractor dict format::
        {"type": "line",  "geometry": [[x, y, z], [x, y, z]]}  # line segment
        {"type": "point", "geometry": [x, y, z]}                # single point

    attractor_score = total_unblocked / total_rays (0–1).
    A score of 0 means no test point can see any attractor.

    Args:
        building_boundary: Closed polygon [[x, y, z], ...].
        attractors: List of attractor geometry dicts (see above).
        obstacles: Polygons that may block the view rays (buildings, walls, etc.).
        piece_length: Test-point spacing along boundary (m).
        return_ray_detail: Include per-ray dicts in output (set False for speed).
    """
    if not attractors:
        return {
            "attractor_score": 0.0,
            "total_unblocked_attractor_rays": 0,
            "total_attractor_rays": 0,
            "test_point_count": 0,
            "per_test_point": [],
        }

    obstacle_polys = [_coerce_polygon_2d(obs) for obs in obstacles]
    obstacle_union = unary_union(obstacle_polys) if obstacle_polys else None
    test_pts = divide_boundary_into_test_points(building_boundary, piece_length=piece_length)

    total_unblocked = 0
    total_rays = 0
    per_point: list[dict[str, Any]] = []

    for tp in test_pts:
        px, py = float(tp["point"][0]), float(tp["point"][1])
        pt_rays: list[dict[str, Any]] = []
        pt_unblocked = 0

        for a_idx, attractor in enumerate(attractors):
            ax, ay = _nearest_point_on_attractor(attractor, px, py)
            ray = LineString([(px, py), (ax, ay)])

            if return_ray_detail:
                blocked = False
                blocked_by: int | None = None
                for obs_idx, obs_poly in enumerate(obstacle_polys):
                    if ray.intersects(obs_poly):
                        blocked = True
                        blocked_by = obs_idx
                        break
            else:
                blocked = obstacle_union is not None and ray.intersects(obstacle_union)

            if not blocked:
                pt_unblocked += 1
                total_unblocked += 1
            total_rays += 1

            if return_ray_detail:
                dist = math.hypot(ax - px, ay - py)
                pt_rays.append({
                    "attractor_index": a_idx,
                    "target_point": [round(ax, 3), round(ay, 3)],
                    "distance_m": round(dist, 3),
                    "blocked": blocked,
                    "blocked_by_obstacle_index": blocked_by,
                })

        entry: dict[str, Any] = {
            "point": tp["point"],
            "segment_index": tp["segment_index"],
            "piece_index": tp["piece_index"],
            "unblocked_count": pt_unblocked,
            "total_count": len(attractors),
        }
        if return_ray_detail:
            entry["attractor_rays"] = pt_rays
        per_point.append(entry)

    attractor_score = total_unblocked / total_rays if total_rays > 0 else 0.0
    return {
        "attractor_score": round(attractor_score, 6),
        "total_unblocked_attractor_rays": total_unblocked,
        "total_attractor_rays": total_rays,
        "test_point_count": len(test_pts),
        "per_test_point": per_point,
    }


def _nearest_point_on_attractor(
    attractor: dict[str, Any],
    px: float,
    py: float,
) -> tuple[float, float]:
    """Return the (x, y) on the attractor geometry nearest to point (px, py)."""
    from shapely.geometry import Point as _SPoint

    atype = attractor.get("type", "point")
    geom = attractor["geometry"]

    if atype == "line":
        line = LineString([(float(p[0]), float(p[1])) for p in geom])
        nearest = line.interpolate(line.project(_SPoint(px, py)))
        return float(nearest.x), float(nearest.y)

    # point: geometry = [x, y, z] or [[x, y, z]]
    if isinstance(geom[0], (list, tuple)):
        g = geom[0]
    else:
        g = geom
    return float(g[0]), float(g[1])


def _coerce_polygon_2d(boundary: list[list[float]]) -> Polygon:
    """Convert boundary (may have z) to a valid Shapely Polygon."""
    points = [(float(p[0]), float(p[1])) for p in boundary]
    poly = Polygon(points)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if not isinstance(poly, Polygon) or poly.area <= 0:
        raise ValueError("obstacle boundary must define a valid non-degenerate polygon")
    return poly
