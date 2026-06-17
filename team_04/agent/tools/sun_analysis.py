"""Sun exposure analysis — the "avoid the worst sun" fitness (Phase 1 of BACKEND_PLAN.md).

Team decision: represent the sun as **one dominant diagonal vector** (a single
azimuth + altitude — e.g. the low western summer sun as the worst case) rather
than a full annual simulation. The tools here are pure (Shapely in / dict out),
deterministic, and carry no LLM or MCP calls, mirroring ``view_analysis.py``.

Geometry conventions
--------------------
* World plane is XY with ``+x = East``, ``+y = North`` (same as every other
  Team 04 tool).
* ``azimuth`` is a compass bearing in degrees, measured **clockwise from North**
  (0 = N, 90 = E, 180 = S, 270 = W). The horizontal direction *toward* the sun
  in plan is therefore ``(sin az, cos az)``.
* ``altitude`` is the sun's angle above the horizon in degrees.

Exposure model
--------------
A vertical facade test point's exposure to one sun vector is the cosine of the
incidence angle on a vertical surface::

    exposure_v = max(0, cos(altitude) · cos(Δ)) · weight

where ``Δ`` is the angle between the facade outward normal and the horizontal
sun direction. ``cos(altitude)`` is large for a *low* sun, which is exactly why
the low western sun is the worst case for west/south-west facades. The vector is
zeroed when an obstacle (projected with its height) casts a shadow over the
point. The per-point score is normalised by the theoretical maximum
(``Σ cos(altitude_v)·weight_v``), so the returned ``sun_exposure_score`` is in
[0, 1] where **lower is better** for the avoid-worst-sun objective.
"""
from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from .view_analysis import _coerce_polygon_2d, divide_boundary_into_test_points

_PLOTLY_IMPORT_ERROR: Exception | None = None
try:
    import plotly.graph_objects as go
except Exception as exc:  # pragma: no cover
    go = None  # type: ignore[assignment]
    _PLOTLY_IMPORT_ERROR = exc


def _ensure_plotly() -> None:
    if _PLOTLY_IMPORT_ERROR is not None:
        raise RuntimeError(
            "plotly is required for 3D sun visualisation — run: pip install plotly"
        ) from _PLOTLY_IMPORT_ERROR


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Worst-case single-diagonal presets (azimuth °CW-from-N, altitude °, weight).
#: ``summer_west`` is the default "one diagonal" mode: a low west-south-west
#: afternoon sun that punishes west / south-west facing facades the most.
WORST_CASE_PRESETS: dict[str, dict[str, float]] = {
    "summer_west":      {"azimuth": 255.0, "altitude": 18.0, "weight": 1.0},
    "summer_southwest": {"azimuth": 225.0, "altitude": 25.0, "weight": 1.0},
    "winter_south":     {"azimuth": 180.0, "altitude": 20.0, "weight": 1.0},
    "summer_noon":      {"azimuth": 180.0, "altitude": 60.0, "weight": 1.0},
}

DEFAULT_WORST_CASE_PRESET = "summer_west"

#: Height assumed for an obstacle supplied as a bare boundary (no height field).
DEFAULT_OBSTACLE_HEIGHT_M = 12.0

#: Hard cap on the shadow ray length so an almost-horizontal sun does not create
#: an effectively infinite shadow.
MAX_SHADOW_REACH_M = 300.0


# ---------------------------------------------------------------------------
# Sun vectors
# ---------------------------------------------------------------------------

def worst_case_sun_vector(preset: str = DEFAULT_WORST_CASE_PRESET) -> dict[str, float]:
    """Return the single dominant sun vector for ``preset`` (the "one diagonal")."""
    if preset not in WORST_CASE_PRESETS:
        raise ValueError(
            f"unknown worst_case_preset {preset!r}; choose from {sorted(WORST_CASE_PRESETS)}"
        )
    return dict(WORST_CASE_PRESETS[preset])


def compute_sun_vectors(
    latitude: float | None = None,
    date: Any = None,
    hours: list[float] | None = None,
    *,
    worst_case_preset: str | None = DEFAULT_WORST_CASE_PRESET,
) -> list[dict[str, float]]:
    """Return a list of ``{azimuth, altitude, weight}`` sun vectors.

    Two modes:

    * **Worst-case (default, zero astronomy):** pass ``worst_case_preset`` (and
      leave the astronomy args ``None``) to get the single dominant diagonal
      vector. This is the team's "one diagonal view" mode.
    * **Multi-hour:** pass ``latitude``, ``date`` and ``hours`` *and* set
      ``worst_case_preset=None`` to compute real solar positions for each hour
      (daylight hours only). Each vector is weighted by ``max(0, sin(altitude))``
      as an irradiance proxy.

    ``date`` accepts ``"YYYY-MM-DD"``, ``"MM-DD"``, a ``(month, day)`` tuple, or
    an integer day-of-year.
    """
    if worst_case_preset is not None:
        return [worst_case_sun_vector(worst_case_preset)]

    if latitude is None or date is None or not hours:
        raise ValueError(
            "multi-hour mode needs latitude, date and hours (or pass worst_case_preset)"
        )

    day = _day_of_year(date)
    vectors: list[dict[str, float]] = []
    for hour in hours:
        azimuth, altitude = _solar_position(float(latitude), day, float(hour))
        if altitude <= 0.0:
            continue  # sun below horizon — no direct exposure
        vectors.append({
            "azimuth": round(azimuth, 3),
            "altitude": round(altitude, 3),
            "weight": round(max(0.0, math.sin(math.radians(altitude))), 4),
            "hour": float(hour),
        })
    return vectors


# ---------------------------------------------------------------------------
# Facade exposure
# ---------------------------------------------------------------------------

def evaluate_sun_exposure(
    building_boundary: list[list[float]],
    sun_vectors: list[dict[str, float]],
    obstacles: list[Any] | None = None,
    *,
    piece_length: float = 2.0,
    return_ray_detail: bool = True,
) -> dict[str, Any]:
    """Evaluate how strongly a building's facades are hit by the sun vectors.

    The boundary is divided into facade test points (reusing
    ``view_analysis.divide_boundary_into_test_points``). For each test point the
    exposure is summed over the sun vectors using the vertical-surface incidence
    model, zeroed for any vector shadowed by an obstacle.

    Args:
        building_boundary: Closed polygon ``[[x, y, z?], ...]``.
        sun_vectors:       List of ``{azimuth, altitude, weight}``.
        obstacles:         Optional obstacles casting shadows. Each entry is
                           either a bare boundary (``[[x, y], ...]`` — a default
                           height is assumed) or a dict
                           ``{"boundary": [...], "height": h}``.
        piece_length:      Test-point spacing along the boundary (m).
        return_ray_detail: Include per-test-point / per-vector detail. Set False
                           for optimizer inner loops.

    Returns a dict with ``sun_exposure_score`` (0–1, **lower = better**), the
    normalising ``max_possible_per_point``, the ``worst_point``, and (when
    ``return_ray_detail``) ``per_test_point`` detail for visualisation.
    """
    if not sun_vectors:
        return {
            "sun_exposure_score": 0.0,
            "max_possible_per_point": 0.0,
            "test_point_count": 0,
            "sun_vectors": [],
            "per_test_point": [],
            "worst_point": None,
        }

    obstacle_shapes = _normalize_obstacles(obstacles)
    obstacle_union = unary_union([poly for poly, _ in obstacle_shapes]) if obstacle_shapes else None

    test_pts = divide_boundary_into_test_points(building_boundary, piece_length=piece_length)
    # Per-point ceiling: a perfectly-facing, unshaded facade.
    max_per_point = sum(
        math.cos(math.radians(_clamp_altitude(v["altitude"]))) * float(v.get("weight", 1.0))
        for v in sun_vectors
    )

    total_norm = 0.0
    per_point: list[dict[str, Any]] = []
    worst: dict[str, Any] | None = None

    for tp in test_pts:
        nx, ny = float(tp["outward_normal"][0]), float(tp["outward_normal"][1])
        px, py = float(tp["point"][0]), float(tp["point"][1])

        point_exposure = 0.0
        vector_detail: list[dict[str, Any]] = []
        for v in sun_vectors:
            sx, sy = _sun_horizontal_unit(v["azimuth"])
            cos_delta = nx * sx + ny * sy  # facade faces the sun when > 0
            altitude = _clamp_altitude(v["altitude"])
            weight = float(v.get("weight", 1.0))
            contrib = max(0.0, math.cos(math.radians(altitude)) * cos_delta) * weight

            blocked = False
            if contrib > 0.0 and obstacle_shapes:
                blocked = _is_shadowed(
                    px, py, nx, ny, sx, sy, altitude,
                    obstacle_shapes, obstacle_union, return_ray_detail,
                )
                if blocked:
                    contrib = 0.0

            point_exposure += contrib
            if return_ray_detail:
                vector_detail.append({
                    "azimuth": v["azimuth"],
                    "altitude": v["altitude"],
                    "cos_delta": round(cos_delta, 4),
                    "exposure": round(contrib, 6),
                    "blocked": blocked,
                })

        norm = point_exposure / max_per_point if max_per_point > 1e-12 else 0.0
        total_norm += norm

        if worst is None or norm > worst["normalized_exposure"]:
            worst = {"point": [px, py], "normalized_exposure": round(norm, 6)}

        if return_ray_detail:
            per_point.append({
                "point": [round(px, 6), round(py, 6)],
                "outward_normal": [round(nx, 6), round(ny, 6)],
                "segment_index": tp["segment_index"],
                "exposure": round(point_exposure, 6),
                "normalized_exposure": round(norm, 6),
                "vectors": vector_detail,
            })

    n = len(test_pts)
    score = total_norm / n if n > 0 else 0.0
    return {
        "sun_exposure_score": round(score, 6),
        "max_possible_per_point": round(max_per_point, 6),
        "test_point_count": n,
        "piece_length_m": piece_length,
        "sun_vectors": list(sun_vectors),
        "worst_point": worst,
        "per_test_point": per_point,
    }


# ---------------------------------------------------------------------------
# Worst site side
# ---------------------------------------------------------------------------

def identify_worst_sun_side(
    site_model: dict[str, Any],
    sun_vectors: list[dict[str, float]],
) -> dict[str, Any]:
    """Identify which site side receives the worst (highest) sun exposure.

    Drives the "place / orient the building to avoid that worst sun" rule: the
    returned ``worst_side`` is the facade direction a sensitive facade or a
    courtyard opening should turn *away* from.

    Returns ``{"available": False, ...}`` when the model lacks a usable boundary.
    """
    boundary = site_model.get("boundary") if isinstance(site_model, dict) else None
    if not isinstance(boundary, list) or len(boundary) < 3 or not sun_vectors:
        return {"available": False, "reason": "site_model boundary missing or no sun vectors"}

    coords = [(float(p[0]), float(p[1])) for p in boundary]
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    cx = sum(p[0] for p in coords) / len(coords)
    cy = sum(p[1] for p in coords) / len(coords)

    # Side labels / cardinal hints from the boundary graph when present.
    graph_edges = (site_model.get("boundary_graph") or {}).get("edges", [])

    max_per = sum(
        math.cos(math.radians(_clamp_altitude(v["altitude"]))) * float(v.get("weight", 1.0))
        for v in sun_vectors
    )

    per_side: list[dict[str, Any]] = []
    n = len(coords)
    for i in range(n):
        ax, ay = coords[i]
        bx, by = coords[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        seg_len = math.hypot(dx, dy)
        if seg_len < 1e-9:
            continue
        mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
        # Outward normal: the perpendicular that points away from the centroid.
        nx, ny = dy / seg_len, -dx / seg_len
        if nx * (mx - cx) + ny * (my - cy) < 0:
            nx, ny = -nx, -ny

        exposure = 0.0
        for v in sun_vectors:
            sx, sy = _sun_horizontal_unit(v["azimuth"])
            cos_delta = nx * sx + ny * sy
            altitude = _clamp_altitude(v["altitude"])
            exposure += max(0.0, math.cos(math.radians(altitude)) * cos_delta) * float(v.get("weight", 1.0))

        edge = graph_edges[i] if i < len(graph_edges) and isinstance(graph_edges[i], dict) else {}
        per_side.append({
            "edge_index": i,
            "label": edge.get("label", f"side_{i}"),
            "cardinal_hint": edge.get("cardinal_hint", _compass_sector(nx, ny)),
            "outward_normal": [round(nx, 6), round(ny, 6)],
            "midpoint": [round(mx, 4), round(my, 4)],
            "length_m": round(seg_len, 4),
            "sun_exposure_score": round(exposure / max_per if max_per > 1e-12 else 0.0, 6),
            "compass_sector": _compass_sector(nx, ny),
        })

    if not per_side:
        return {"available": False, "reason": "no usable sides"}

    worst = max(per_side, key=lambda s: s["sun_exposure_score"])
    best = min(per_side, key=lambda s: s["sun_exposure_score"])
    return {
        "available": True,
        "worst_side": worst,
        "best_side": best,
        "worst_compass_sector": worst["compass_sector"],
        "per_side": per_side,
        "sun_vectors": list(sun_vectors),
    }


# ---------------------------------------------------------------------------
# 3D height-aware sun exposure (practical multi-building mutual shading)
# ---------------------------------------------------------------------------

def evaluate_sun_exposure_3d(
    building_boundary: list[list[float]],
    building_height: float,
    sun_vectors: list[dict[str, float]],
    obstacles_with_heights: list[dict[str, Any]] | None = None,
    *,
    piece_length: float = 3.0,
    floor_height: float = 3.0,
    return_ray_detail: bool = True,
) -> dict[str, Any]:
    """Height-aware facade sun exposure with real per-floor mutual shading.

    This is the practical, multi-building version of ``evaluate_sun_exposure``.
    The building's side faces are divided into a facade cell grid (reusing
    ``view_3d.build_facade_cells`` — one cell per ``piece_length`` along each edge
    and per floor). For each cell the exposure is summed over the sun vectors,
    and an obstacle of height ``h`` only shades a cell at height ``z`` when
    ``h > z`` **and** the obstacle lies within the horizontal shadow reach
    ``(h - z) / tan(altitude)``. So a 12 m neighbour shades a building's lower
    floors but the floors that rise above 12 m keep their sun — exactly the
    mutual-shading behaviour a flat 2D projection cannot capture.

    ``obstacles_with_heights`` is a list of ``{"boundary": [...], "height": h}``
    (the *other* buildings + external obstacles; never the building itself).

    Returns ``sun_exposure_score_3d`` (0–1, **lower = better**), ``per_floor``
    exposure, and (when ``return_ray_detail``) the facade ``cells`` with a
    normalized ``sun_exposure`` field filled in for 3D colouring.
    """
    from .view_3d import build_facade_cells

    if not sun_vectors:
        return {
            "sun_exposure_score_3d": 0.0,
            "n_floors": max(1, int(building_height / floor_height)),
            "per_floor": [],
            "cells": [],
            "sun_vectors": [],
        }

    cells = build_facade_cells(
        building_boundary, building_height,
        piece_length=piece_length, floor_height=floor_height,
    )
    n_floors = max(1, int(building_height / floor_height))
    obstacle_shapes = _coerce_obstacles_3d(obstacles_with_heights)

    max_per_cell = sum(
        math.cos(math.radians(_clamp_altitude(v["altitude"]))) * float(v.get("weight", 1.0))
        for v in sun_vectors
    )

    per_floor_sum: dict[int, list[float]] = {k: [0.0, 0] for k in range(n_floors)}
    total_norm = 0.0

    for cell in cells:
        nx, ny = cell["nx"], cell["ny"]
        px, py, pz = cell["px"], cell["py"], cell["pz"]

        exposure = 0.0
        for v in sun_vectors:
            sx, sy = _sun_horizontal_unit(v["azimuth"])
            cos_delta = nx * sx + ny * sy
            altitude = _clamp_altitude(v["altitude"])
            weight = float(v.get("weight", 1.0))
            contrib = max(0.0, math.cos(math.radians(altitude)) * cos_delta) * weight
            if contrib > 0.0 and obstacle_shapes and _is_shadowed_3d(
                px, py, pz, nx, ny, sx, sy, altitude, obstacle_shapes
            ):
                contrib = 0.0
            exposure += contrib

        norm = exposure / max_per_cell if max_per_cell > 1e-12 else 0.0
        cell["sun_exposure"] = round(norm, 6)
        total_norm += norm
        k = cell["floor"] - 1
        per_floor_sum[k][0] += norm
        per_floor_sum[k][1] += 1

    n = len(cells)
    score = total_norm / n if n > 0 else 0.0
    per_floor = [
        {
            "z_level": round((k + 0.5) * floor_height, 2),
            "floor_number": k + 1,
            "sun_exposure_score": round(per_floor_sum[k][0] / per_floor_sum[k][1], 6)
            if per_floor_sum[k][1] else 0.0,
            "cell_count": per_floor_sum[k][1],
        }
        for k in range(n_floors)
    ]

    out: dict[str, Any] = {
        "sun_exposure_score_3d": round(score, 6),
        "n_floors": n_floors,
        "floor_height_m": floor_height,
        "building_height_m": building_height,
        "max_possible_per_cell": round(max_per_cell, 6),
        "per_floor": per_floor,
        "sun_vectors": list(sun_vectors),
    }
    if return_ray_detail:
        out["cells"] = cells
    return out


def visualize_sun_3d(
    site_boundary: list[list[float]],
    buildings: list[dict[str, Any]],
    sun_vectors: list[dict[str, float]],
    *,
    obstacles: list[dict[str, Any]] | None = None,
    buildable_zone_boundary: list[list[float]] | None = None,
    sun_results: list[dict[str, Any]] | None = None,
    piece_length: float = 3.0,
    floor_height: float = 3.0,
    title: str = "3D Sun Exposure",
) -> Any:
    """Interactive plotly 3D scene with facades coloured by sun exposure.

    Each building's side faces are a continuous heatmap (blue = shaded/cool →
    red = full worst-sun hit), so the mutual shading between buildings reads
    directly: a tall building's shadow shows up as a cool band on the lower
    floors of its neighbour. The dominant sun vector is drawn as a bundle of
    parallel rays at its real altitude.

    ``buildings`` / ``obstacles`` are ``{boundary, height, label?}`` dicts.
    ``sun_results`` (one ``evaluate_sun_exposure_3d`` per building, with
    ``cells``) is reused when supplied; otherwise it is computed here so each
    building is shaded by every *other* building and obstacle.
    """
    _ensure_plotly()
    from .view_3d import _fan_triangulate, _prism_traces

    traces: list[Any] = []

    # Site ground plane.
    site_coords = [(float(p[0]), float(p[1])) for p in site_boundary[:-1]]
    sx_, sy_ = zip(*site_coords)
    traces.append(go.Mesh3d(
        x=list(sx_), y=list(sy_), z=[0.0] * len(sx_),
        color="#e8e4dc", opacity=0.5, name="Site", showlegend=True,
        **_fan_triangulate(len(sx_)),
    ))

    if buildable_zone_boundary:
        traces.append(go.Scatter3d(
            x=[p[0] for p in buildable_zone_boundary],
            y=[p[1] for p in buildable_zone_boundary],
            z=[0.05] * len(buildable_zone_boundary),
            mode="lines", line=dict(color="#1a8cff", width=3, dash="dash"),
            name="Buildable zone", showlegend=True,
        ))

    obstacles = obstacles or []
    for oi, obs in enumerate(obstacles):
        traces.extend(_prism_traces(
            obs["boundary"], float(obs.get("height", 10.0)), "#7f8c8d",
            obs.get("label", f"Obstacle {oi + 1}"), opacity=0.55,
            showlegend=(oi == 0), legend_group="Obstacles",
        ))

    # Compute sun_results lazily so each building is shaded by the others.
    if sun_results is None:
        sun_results = []
        for bi, bld in enumerate(buildings):
            others = [
                {"boundary": b["boundary"], "height": float(b.get("height", 12.0))}
                for j, b in enumerate(buildings) if j != bi
            ] + [
                {"boundary": o["boundary"], "height": float(o.get("height", 10.0))}
                for o in obstacles
            ]
            sun_results.append(evaluate_sun_exposure_3d(
                bld["boundary"], float(bld.get("height", 12.0)), sun_vectors,
                others, piece_length=piece_length, floor_height=floor_height,
            ))

    for bi, bld in enumerate(buildings):
        h = float(bld.get("height", 12.0))
        label = bld.get("label", f"Building {bi + 1}")
        traces.extend(_prism_traces(bld["boundary"], h, "#bdc3c7", label,
                                    opacity=0.12, showlegend=True))
        cells = (sun_results[bi] or {}).get("cells", []) if bi < len(sun_results) else []
        if cells:
            traces.append(_sun_facade_trace(cells, bi))

    traces.extend(_sun_ray_traces(site_boundary, sun_vectors))

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=title,
        scene=dict(
            xaxis_title="X (m)", yaxis_title="Y (m)", zaxis_title="Z (m)",
            aspectmode="data", camera=dict(eye=dict(x=1.6, y=-1.6, z=1.1)),
        ),
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.75)"),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _coerce_obstacles_3d(obstacles: list[dict[str, Any]] | None) -> list[tuple[Polygon, float]]:
    """Coerce ``{boundary, height}`` obstacle dicts into ``(polygon, height)``."""
    shapes: list[tuple[Polygon, float]] = []
    for obs in obstacles or []:
        bnd = obs.get("boundary") or obs.get("geometry") if isinstance(obs, dict) else obs
        height = float(obs.get("height", DEFAULT_OBSTACLE_HEIGHT_M)) if isinstance(obs, dict) else DEFAULT_OBSTACLE_HEIGHT_M
        if not bnd:
            continue
        try:
            shapes.append((_coerce_polygon_2d(bnd), max(0.0, height)))
        except Exception:
            continue
    return shapes


def _is_shadowed_3d(
    px: float, py: float, pz: float,
    nx: float, ny: float,
    sx: float, sy: float,
    altitude_deg: float,
    obstacle_shapes: list[tuple[Polygon, float]],
    offset_distance: float = 0.1,
) -> bool:
    """True when a taller obstacle shadows a facade cell at height ``pz``.

    An obstacle of height ``h`` only shades a point at height ``pz`` when
    ``h > pz``; the shadow reaches ``(h - pz) / tan(altitude)`` horizontally.
    """
    tan_alt = math.tan(math.radians(altitude_deg))
    if tan_alt <= 1e-9:
        return False
    ox = px + nx * offset_distance
    oy = py + ny * offset_distance
    for poly, height in obstacle_shapes:
        if height <= pz:
            continue  # obstacle is shorter than this cell — cannot shade it
        reach = min(MAX_SHADOW_REACH_M, (height - pz) / tan_alt)
        if reach <= 0.0:
            continue
        ray = LineString([(ox, oy), (ox + sx * reach, oy + sy * reach)])
        if ray.intersects(poly):
            return True
    return False


def _sun_facade_trace(cells: list[dict[str, Any]], building_index: int) -> Any:
    """One go.Mesh3d for a building's facades, vertex intensity = sun exposure."""
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    inten: list[float] = []
    i_idx: list[int] = []
    j_idx: list[int] = []
    k_idx: list[int] = []

    for cell in cells:
        x1, y1, x2, y2 = cell["x1"], cell["y1"], cell["x2"], cell["y2"]
        t0, t1 = cell["t0"], cell["t1"]
        z_bot, z_top = cell["z_bot"], cell["z_top"]
        e = float(cell.get("sun_exposure", 0.0))

        bx0 = x1 + t0 * (x2 - x1); by0 = y1 + t0 * (y2 - y1)
        bx1 = x1 + t1 * (x2 - x1); by1 = y1 + t1 * (y2 - y1)
        base = len(xs)
        xs.extend([bx0, bx1, bx1, bx0])
        ys.extend([by0, by1, by1, by0])
        zs.extend([z_bot, z_bot, z_top, z_top])
        inten.extend([e, e, e, e])
        i_idx.extend([base, base])
        j_idx.extend([base + 1, base + 2])
        k_idx.extend([base + 2, base + 3])

    return go.Mesh3d(
        x=xs, y=ys, z=zs, i=i_idx, j=j_idx, k=k_idx,
        intensity=inten, intensitymode="vertex",
        colorscale="YlOrRd", cmin=0.0, cmax=1.0,
        showscale=(building_index == 0),
        colorbar=dict(title="sun exposure", x=1.0) if building_index == 0 else None,
        opacity=0.95, flatshading=True,
        name=f"B{building_index + 1} sun facade",
        showlegend=False,
    )


def _sun_ray_traces(
    site_boundary: list[list[float]],
    sun_vectors: list[dict[str, float]],
) -> list[Any]:
    """Draw the dominant sun vector as a small bundle of parallel rays."""
    if not sun_vectors:
        return []
    sun = max(sun_vectors, key=lambda v: float(v.get("weight", 1.0)))
    xs = [float(p[0]) for p in site_boundary]
    ys = [float(p[1]) for p in site_boundary]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    span = max(max(xs) - min(xs), max(ys) - min(ys))

    az = math.radians(sun["azimuth"])
    alt = math.radians(_clamp_altitude(sun["altitude"]))
    # 3D unit vector pointing toward the sun.
    ux, uy, uz = math.sin(az) * math.cos(alt), math.cos(az) * math.cos(alt), math.sin(alt)
    L = span * 0.9

    rx: list[float] = []
    ry: list[float] = []
    rz: list[float] = []
    for off in (-0.3, 0.0, 0.3):
        # Targets spread across the site centre; rays fly from the sun inward.
        tx, ty = cx + off * span * 0.5, cy + off * span * 0.5
        rx.extend([tx + ux * L, tx, None])
        ry.extend([ty + uy * L, ty, None])
        rz.extend([uz * L, 0.0, None])
    return [go.Scatter3d(
        x=rx, y=ry, z=rz, mode="lines",
        line=dict(color="#f39c12", width=5),
        name=f"sun az {sun['azimuth']}° alt {sun['altitude']}°",
        showlegend=True,
    )]


def _sun_horizontal_unit(azimuth_deg: float) -> tuple[float, float]:
    """Horizontal unit vector pointing *toward* the sun (compass CW from North)."""
    a = math.radians(float(azimuth_deg))
    return math.sin(a), math.cos(a)


def _clamp_altitude(altitude_deg: float) -> float:
    """Keep altitude in (0, 90) so cos/tan stay well defined."""
    return min(89.0, max(1.0, float(altitude_deg)))


def _compass_sector(nx: float, ny: float) -> str:
    """Map an outward normal to one of 8 compass sectors."""
    az = (math.degrees(math.atan2(nx, ny)) + 360.0) % 360.0  # CW from North
    sectors = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return sectors[int((az + 22.5) % 360.0 // 45.0)]


def _normalize_obstacles(obstacles: list[Any] | None) -> list[tuple[Polygon, float]]:
    """Coerce mixed obstacle inputs into ``(polygon, height)`` pairs."""
    shapes: list[tuple[Polygon, float]] = []
    for obs in obstacles or []:
        if isinstance(obs, dict):
            bnd = obs.get("boundary") or obs.get("geometry")
            height = float(obs.get("height", DEFAULT_OBSTACLE_HEIGHT_M))
        else:
            bnd = obs
            height = DEFAULT_OBSTACLE_HEIGHT_M
        if not bnd:
            continue
        try:
            shapes.append((_coerce_polygon_2d(bnd), max(0.0, height)))
        except Exception:
            continue
    return shapes


def _is_shadowed(
    px: float, py: float,
    nx: float, ny: float,
    sx: float, sy: float,
    altitude_deg: float,
    obstacle_shapes: list[tuple[Polygon, float]],
    obstacle_union: Any,
    return_ray_detail: bool,
    offset_distance: float = 0.05,
) -> bool:
    """True when an obstacle casts a shadow over the point for this sun vector.

    A shadow ray is cast from the point toward the sun. Obstacle ``i`` shades the
    point if the ray reaches it within ``height_i / tan(altitude)`` — the
    horizontal extent of that obstacle's shadow.
    """
    tan_alt = math.tan(math.radians(altitude_deg))
    ox = px + nx * offset_distance
    oy = py + ny * offset_distance

    if not return_ray_detail and obstacle_union is not None:
        # Fast path: one reach for the tallest obstacle, single union check.
        reach = min(MAX_SHADOW_REACH_M, max(h for _, h in obstacle_shapes) / tan_alt) if tan_alt > 1e-9 else MAX_SHADOW_REACH_M
        ray = LineString([(ox, oy), (ox + sx * reach, oy + sy * reach)])
        return bool(ray.intersects(obstacle_union))

    for poly, height in obstacle_shapes:
        reach = min(MAX_SHADOW_REACH_M, height / tan_alt) if tan_alt > 1e-9 else MAX_SHADOW_REACH_M
        if reach <= 0.0:
            continue
        ray = LineString([(ox, oy), (ox + sx * reach, oy + sy * reach)])
        if ray.intersects(poly):
            return True
    return False


def _day_of_year(date: Any) -> int:
    """Resolve a date spec to a day-of-year integer (1–365)."""
    if isinstance(date, int):
        return max(1, min(365, date))
    if isinstance(date, (tuple, list)) and len(date) == 2:
        month, day = int(date[0]), int(date[1])
    elif isinstance(date, str):
        parts = [int(p) for p in date.replace("/", "-").split("-") if p.strip()]
        if len(parts) == 3:      # YYYY-MM-DD
            month, day = parts[1], parts[2]
        elif len(parts) == 2:    # MM-DD
            month, day = parts[0], parts[1]
        else:
            raise ValueError(f"unrecognised date {date!r}")
    else:
        raise ValueError(f"unrecognised date {date!r}")
    cumulative = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    return cumulative[max(0, min(11, month - 1))] + day


def _solar_position(latitude_deg: float, day_of_year: int, hour: float) -> tuple[float, float]:
    """Approximate (azimuth °CW-from-N, altitude °) for a latitude/day/solar hour."""
    decl = 23.45 * math.sin(math.radians(360.0 * (284 + day_of_year) / 365.0))
    hour_angle = 15.0 * (hour - 12.0)  # degrees; solar noon = 0

    lat = math.radians(latitude_deg)
    d = math.radians(decl)
    h = math.radians(hour_angle)

    sin_alt = math.sin(lat) * math.sin(d) + math.cos(lat) * math.cos(d) * math.cos(h)
    sin_alt = max(-1.0, min(1.0, sin_alt))
    altitude = math.degrees(math.asin(sin_alt))

    cos_alt = math.cos(math.asin(sin_alt))
    if abs(cos_alt) < 1e-9:
        return 180.0, altitude
    cos_az = (math.sin(d) - math.sin(lat) * sin_alt) / (math.cos(lat) * cos_alt)
    cos_az = max(-1.0, min(1.0, cos_az))
    azimuth = math.degrees(math.acos(cos_az))  # measured from North, 0–180
    if hour_angle > 0:  # afternoon → sun swings west
        azimuth = 360.0 - azimuth
    return azimuth % 360.0, altitude
