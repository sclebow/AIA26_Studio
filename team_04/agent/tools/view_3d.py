"""3D view analysis and plotly visualisation.

Facade grid approach
--------------------
Each side face of a building is divided into a rectangular cell grid:

  - Horizontal: cells of ~piece_length metres along the edge
  - Vertical  : one cell per floor (height = floor_height)

One outward-normal ray is cast from each cell centroid (offset 0.1 m outward
to avoid self-intersection with the building polygon).  Obstacles only block
rays at heights where obstacle.height >= cell z-centre.

Facade cell colouring
---------------------
  Green  → unblocked  (ray travels full ray_length without hitting anything)
  Red    → blocked    (ray intersects an obstacle)

The coloured quads are rendered directly ON the building facade as
go.Mesh3d panels, giving a heatmap that reads intuitively in 3D.

3D plotly visualisation
-----------------------
Pure plotly — no topologicpy dependency:
  Site           → go.Mesh3d flat ground slab
  Buildable zone → go.Scatter3d dashed boundary outline
  Obstacles      → go.Mesh3d dark-red extruded prisms
  Buildings      → go.Mesh3d solid prism (semi-transparent shell)
  Facade panels  → go.Mesh3d green / red quads on every side face
  Ray arrows     → go.Scatter3d short outward lines (optional)
  Attractors     → go.Scatter3d horizontal line at z = 0
"""
from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Polygon
from shapely.geometry.polygon import orient as _orient
from shapely.ops import unary_union

from .view_analysis import _coerce_polygon_2d, _cast_rays_from_point

_PLOTLY_IMPORT_ERROR: Exception | None = None
try:
    import plotly.graph_objects as go
except Exception as exc:  # pragma: no cover
    go = None  # type: ignore[assignment]
    _PLOTLY_IMPORT_ERROR = exc

# Small outward push so test points sit just outside the polygon surface
_FACADE_OFFSET = 0.1


# ---------------------------------------------------------------------------
# Facade grid helpers
# ---------------------------------------------------------------------------

def _boundary_to_ccw_coords(
    boundary: list[list[float]],
) -> list[tuple[float, float]]:
    """Return the CCW exterior ring (no closing repeat) as (x, y) pairs."""
    pts = [(float(p[0]), float(p[1])) for p in boundary[:-1]]
    poly = Polygon(pts)
    poly = _orient(poly, sign=1.0)
    return list(poly.exterior.coords)[:-1]


def build_facade_cells(
    boundary: list[list[float]],
    building_height: float,
    *,
    piece_length: float = 3.0,
    floor_height: float = 3.0,
) -> list[dict[str, Any]]:
    """
    Divide every side face of a building into a grid of rectangular cells.

    Returns a list of dicts, one per cell:
        px, py, pz   — world-space centroid (test point, offset outward)
        nx, ny       — outward unit normal of the parent edge
        x1, y1,      — edge start world coords
        x2, y2       — edge end world coords
        t0, t1       — parametric range along edge [0, 1]
        z_bot, z_top — vertical range of this cell
        edge_index   — parent boundary edge index
        floor        — 1-based floor number
        blocked      — False initially; set by evaluate_building_views_3d
    """
    coords = _boundary_to_ccw_coords(boundary)
    n = len(coords)
    n_floors = max(1, int(building_height / floor_height))
    cells: list[dict[str, Any]] = []

    for ei in range(n):
        x1, y1 = coords[ei]
        x2, y2 = coords[(ei + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        if L < 1e-6:
            continue

        # Outward normal for CCW polygon: right-perpendicular of edge direction
        nx_e, ny_e = dy / L, -dx / L
        n_h = max(1, round(L / piece_length))

        for hi in range(n_h):
            t0 = hi / n_h
            t1 = (hi + 1) / n_h
            tc = (t0 + t1) / 2

            # World-space centroid on the edge surface
            cx = x1 + tc * (x2 - x1)
            cy = y1 + tc * (y2 - y1)

            for k in range(n_floors):
                z_bot = k * floor_height
                z_top = (k + 1) * floor_height
                z_ctr = (z_bot + z_top) / 2

                cells.append({
                    # Test point (slightly outside facade)
                    "px": cx + nx_e * _FACADE_OFFSET,
                    "py": cy + ny_e * _FACADE_OFFSET,
                    "pz": z_ctr,
                    # Outward normal
                    "nx": nx_e, "ny": ny_e,
                    # Corner info for quad rendering
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "t0": t0, "t1": t1,
                    "z_bot": z_bot, "z_top": z_top,
                    # Metadata
                    "edge_index": ei,
                    "floor": k + 1,
                    # Result (filled later)
                    "blocked": True,
                })

    return cells


# ---------------------------------------------------------------------------
# Height-aware 3D ray evaluation
# ---------------------------------------------------------------------------

def evaluate_building_views_3d(
    building_boundary: list[list[float]],
    building_height: float,
    obstacles_with_heights: list[dict[str, Any]],
    *,
    piece_length: float = 3.0,
    floor_height: float = 3.0,
    ray_length: float = 80.0,
    return_ray_detail: bool = True,
) -> dict[str, Any]:
    """
    Evaluate views from every facade grid cell of a building.

    For each floor z, only obstacles whose height >= z block rays.
    Upper floors can therefore "see over" shorter obstacles.

    Args:
        building_boundary:       Closed [[x, y, z], …] polygon.
        building_height:         Total building height (m).
        obstacles_with_heights:  List of {``boundary``: [...], ``height``: float}.
        piece_length:            Horizontal cell size along each edge (m).
        floor_height:            Storey height (m).  Default 3 m.
        ray_length:              Maximum ray distance (m).
        return_ray_detail:       Include ``facade_cells`` in result.

    Returns dict:
        view_score_3d, total_unblocked_rays, total_rays, n_floors,
        per_floor  [{z_level, floor_number, view_score, unblocked, total}],
        facade_cells  (when return_ray_detail=True) — cell list with
                      ``blocked`` field filled in.
    """
    cells = build_facade_cells(
        building_boundary, building_height,
        piece_length=piece_length, floor_height=floor_height,
    )
    n_floors = max(1, int(building_height / floor_height))

    # Pre-compute per-floor obstacle unions (expensive — do once)
    floor_obs: dict[int, tuple[list[Polygon], Any]] = {}
    for k in range(n_floors):
        z = (k + 0.5) * floor_height
        blocking = [
            obs["boundary"]
            for obs in obstacles_with_heights
            if obs.get("height", float("inf")) >= z
        ]
        obs_polys = [_coerce_polygon_2d(b) for b in blocking]
        obs_union = unary_union(obs_polys) if obs_polys else None
        floor_obs[k] = (obs_polys, obs_union)

    per_floor_stats: dict[int, dict[str, int]] = {
        k: {"unblocked": 0, "total": 0} for k in range(n_floors)
    }
    total_unblocked = 0

    for cell in cells:
        k = cell["floor"] - 1
        obs_polys, obs_union = floor_obs[k]

        result = _cast_rays_from_point(
            point=[cell["px"], cell["py"]],
            outward_normal=[cell["nx"], cell["ny"]],
            obstacle_polys=obs_polys,
            obstacle_union=obs_union,
            ray_count=1,
            ray_spread_degrees=0.0,
            ray_length=ray_length,
            return_ray_detail=False,
        )
        blocked = result["unblocked_count"] == 0
        cell["blocked"] = blocked

        per_floor_stats[k]["total"] += 1
        if not blocked:
            per_floor_stats[k]["unblocked"] += 1
            total_unblocked += 1

    total_rays = len(cells)
    view_score = total_unblocked / total_rays if total_rays > 0 else 0.0

    per_floor = [
        {
            "z_level": round((k + 0.5) * floor_height, 2),
            "floor_number": k + 1,
            "view_score": (
                round(per_floor_stats[k]["unblocked"] / per_floor_stats[k]["total"], 6)
                if per_floor_stats[k]["total"] > 0 else 0.0
            ),
            "unblocked": per_floor_stats[k]["unblocked"],
            "total": per_floor_stats[k]["total"],
        }
        for k in range(n_floors)
    ]

    out: dict[str, Any] = {
        "view_score_3d": round(view_score, 6),
        "total_unblocked_rays": total_unblocked,
        "total_rays": total_rays,
        "n_floors": n_floors,
        "floor_height_m": floor_height,
        "building_height_m": building_height,
        "per_floor": per_floor,
    }
    if return_ray_detail:
        out["facade_cells"] = cells
    return out


# ---------------------------------------------------------------------------
# 3D plotly visualisation
# ---------------------------------------------------------------------------

def visualize_3d(
    site_boundary: list[list[float]],
    buildings: list[dict[str, Any]],
    obstacles: list[dict[str, Any]],
    *,
    buildable_zone_boundary: list[list[float]] | None = None,
    attractors: list[dict[str, Any]] | None = None,
    view_results: list[dict[str, Any]] | None = None,
    title: str = "3D Site View",
    ray_length: float = 8.0,
    show_rays: bool = True,
) -> Any:
    """
    Create an interactive plotly 3D figure.

    Args:
        site_boundary:           Closed [[x,y,z]…] site polygon.
        buildings:               List of {boundary, height, label?, color?}.
        obstacles:               List of {boundary, height, label?, color?}.
        buildable_zone_boundary: Optional inset boundary (dashed blue outline).
        attractors:              List of {type, geometry} attractor dicts.
        view_results:            One ``evaluate_building_views_3d`` result per
                                 building.  When supplied, facade panels are
                                 coloured green/red and ray arrows are drawn.
        title:                   Figure title.
        ray_length:              Length of outward ray arrows (m).
        show_rays:               Draw ray arrow lines (default True).

    Returns:
        plotly Figure.
    """
    _ensure_plotly()
    traces: list[Any] = []

    # Site ground plane
    site_coords = [(float(p[0]), float(p[1])) for p in site_boundary[:-1]]
    sx, sy = zip(*site_coords)
    tri = _fan_triangulate(len(sx))
    traces.append(go.Mesh3d(
        x=list(sx), y=list(sy), z=[0.0] * len(sx),
        color="#e8e4dc", opacity=0.5,
        name="Site", showlegend=True,
        **tri,
    ))

    # Buildable zone dashed outline
    if buildable_zone_boundary:
        bz_x = [p[0] for p in buildable_zone_boundary]
        bz_y = [p[1] for p in buildable_zone_boundary]
        traces.append(go.Scatter3d(
            x=bz_x, y=bz_y, z=[0.05] * len(bz_x),
            mode="lines",
            line=dict(color="#1a8cff", width=3, dash="dash"),
            name="Buildable zone", showlegend=True,
        ))

    # Attractors
    for ai, att in enumerate((attractors or [])):
        if att.get("type") == "line":
            g = att["geometry"]
            traces.append(go.Scatter3d(
                x=[g[0][0], g[1][0]], y=[g[0][1], g[1][1]], z=[0.0, 0.0],
                mode="lines", line=dict(color="#1a8cff", width=6),
                name="Attractor" if ai == 0 else None,
                showlegend=(ai == 0),
            ))

    # Obstacles
    for oi, obs in enumerate(obstacles):
        h = float(obs.get("height", 10.0))
        label = obs.get("label", f"Obstacle {oi + 1}")
        color = obs.get("color", "#c0392b")
        traces.extend(_prism_traces(obs["boundary"], h, color, label,
                                    opacity=0.80, showlegend=(oi == 0),
                                    legend_group="Obstacles"))

    # Buildings + facade heatmap
    bld_colors = ["#2980b9", "#e67e22", "#27ae60", "#8e44ad", "#16a085"]
    for bi, bld in enumerate(buildings):
        h = float(bld.get("height", 12.0))
        color = bld.get("color", bld_colors[bi % len(bld_colors)])
        label = bld.get("label", f"Building {bi + 1}")

        # Solid shell (semi-transparent so facade panels show through)
        traces.extend(_prism_traces(bld["boundary"], h, color, label,
                                    opacity=0.25, showlegend=True))

        # Facade heatmap panels + rays (if view result provided)
        if view_results and bi < len(view_results):
            vr = view_results[bi]
            cells = vr.get("facade_cells", [])
            if cells:
                traces.extend(_facade_panel_traces(cells, bi, label))
                if show_rays:
                    traces.extend(_facade_ray_traces(cells, ray_length, bi))

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=title,
        scene=dict(
            xaxis_title="X (m)", yaxis_title="Y (m)", zaxis_title="Z (m)",
            aspectmode="data",
            camera=dict(eye=dict(x=1.5, y=-1.5, z=1.2)),
        ),
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.75)"),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


# ---------------------------------------------------------------------------
# Facade panel rendering
# ---------------------------------------------------------------------------

def _facade_panel_traces(
    cells: list[dict[str, Any]],
    building_index: int,
    building_label: str,
) -> list[Any]:
    """
    Build two go.Mesh3d traces — one green (unblocked), one red (blocked) —
    each containing all relevant facade quad panels for this building.
    """
    clear_xyz: list[list[float]] = [[], [], []]
    block_xyz: list[list[float]] = [[], [], []]
    clear_ijk: list[list[int]] = [[], [], []]
    block_ijk: list[list[int]] = [[], [], []]

    def _add_quad(
        buf_xyz: list[list[float]],
        buf_ijk: list[list[int]],
        cell: dict[str, Any],
    ) -> None:
        x1, y1 = cell["x1"], cell["y1"]
        x2, y2 = cell["x2"], cell["y2"]
        t0, t1 = cell["t0"], cell["t1"]
        z_bot, z_top = cell["z_bot"], cell["z_top"]

        # 4 corners: bottom-left, bottom-right, top-right, top-left
        bx0 = x1 + t0 * (x2 - x1)
        by0 = y1 + t0 * (y2 - y1)
        bx1 = x1 + t1 * (x2 - x1)
        by1 = y1 + t1 * (y2 - y1)

        base = len(buf_xyz[0])
        buf_xyz[0].extend([bx0, bx1, bx1, bx0])
        buf_xyz[1].extend([by0, by1, by1, by0])
        buf_xyz[2].extend([z_bot, z_bot, z_top, z_top])

        # Two triangles: (0,1,2) and (0,2,3)
        buf_ijk[0].extend([base, base])
        buf_ijk[1].extend([base + 1, base + 2])
        buf_ijk[2].extend([base + 2, base + 3])

    for cell in cells:
        if cell["blocked"]:
            _add_quad(block_xyz, block_ijk, cell)
        else:
            _add_quad(clear_xyz, clear_ijk, cell)

    traces = []
    prefix = f"B{building_index + 1} "

    if clear_xyz[0]:
        traces.append(go.Mesh3d(
            x=clear_xyz[0], y=clear_xyz[1], z=clear_xyz[2],
            i=clear_ijk[0], j=clear_ijk[1], k=clear_ijk[2],
            color="#2ecc71", opacity=0.9,
            name=prefix + "unblocked facade",
            showlegend=(building_index == 0),
            legendgroup="unblocked_facade",
            flatshading=True,
        ))

    if block_xyz[0]:
        traces.append(go.Mesh3d(
            x=block_xyz[0], y=block_xyz[1], z=block_xyz[2],
            i=block_ijk[0], j=block_ijk[1], k=block_ijk[2],
            color="#e74c3c", opacity=0.9,
            name=prefix + "blocked facade",
            showlegend=(building_index == 0),
            legendgroup="blocked_facade",
            flatshading=True,
        ))

    return traces


def _facade_ray_traces(
    cells: list[dict[str, Any]],
    ray_length: float,
    building_index: int,
) -> list[Any]:
    """Short outward arrow lines from each facade cell centroid."""
    clear_x: list[float] = []
    clear_y: list[float] = []
    clear_z: list[float] = []
    block_x: list[float] = []
    block_y: list[float] = []
    block_z: list[float] = []

    for cell in cells:
        px, py, pz = cell["px"], cell["py"], cell["pz"]
        nx, ny = cell["nx"], cell["ny"]
        ex = px + nx * ray_length
        ey = py + ny * ray_length

        if cell["blocked"]:
            block_x.extend([px, ex, None])
            block_y.extend([py, ey, None])
            block_z.extend([pz, pz, None])
        else:
            clear_x.extend([px, ex, None])
            clear_y.extend([py, ey, None])
            clear_z.extend([pz, pz, None])

    traces = []
    prefix = f"B{building_index + 1} "
    if clear_x:
        traces.append(go.Scatter3d(
            x=clear_x, y=clear_y, z=clear_z,
            mode="lines", line=dict(color="#27ae60", width=1),
            name=prefix + "clear rays",
            showlegend=(building_index == 0),
            legendgroup="clear_rays",
        ))
    if block_x:
        traces.append(go.Scatter3d(
            x=block_x, y=block_y, z=block_z,
            mode="lines", line=dict(color="#c0392b", width=1),
            name=prefix + "blocked rays",
            showlegend=(building_index == 0),
            legendgroup="blocked_rays",
        ))
    return traces


# ---------------------------------------------------------------------------
# Prism geometry helpers
# ---------------------------------------------------------------------------

def _prism_traces(
    boundary: list[list[float]],
    height: float,
    color: str,
    name: str,
    *,
    opacity: float = 0.8,
    showlegend: bool = True,
    legend_group: str = "",
) -> list[Any]:
    """Extruded polygon prism as go.Mesh3d."""
    pts = [(float(p[0]), float(p[1])) for p in boundary[:-1]]
    n = len(pts)
    xs = [p[0] for p in pts] + [p[0] for p in pts]
    ys = [p[1] for p in pts] + [p[1] for p in pts]
    zs = [0.0] * n + [height] * n

    # Bottom cap
    i_b = [0] * (n - 2)
    j_b = list(range(1, n - 1))
    k_b = list(range(2, n))
    # Top cap (reversed winding)
    i_t = [n] * (n - 2)
    j_t = [n + k for k in range(2, n)]
    k_t = [n + j for j in range(1, n - 1)]
    # Side quads → 2 triangles each
    i_s: list[int] = []
    j_s: list[int] = []
    k_s: list[int] = []
    for idx in range(n):
        nxt = (idx + 1) % n
        i_s += [idx, nxt]
        j_s += [nxt, n + nxt]
        k_s += [n + idx, n + idx]

    return [go.Mesh3d(
        x=xs, y=ys, z=zs,
        i=i_b + i_t + i_s,
        j=j_b + j_t + j_s,
        k=k_b + k_t + k_s,
        color=color, opacity=opacity,
        name=name, showlegend=showlegend,
        legendgroup=legend_group or name,
        flatshading=True,
        lighting=dict(ambient=0.6, diffuse=0.8),
    )]


def _fan_triangulate(n: int) -> dict[str, list[int]]:
    """Fan triangulation from vertex 0 for a flat polygon of n vertices."""
    if n < 3:
        return {"i": [], "j": [], "k": []}
    return {
        "i": [0] * (n - 2),
        "j": list(range(1, n - 1)),
        "k": list(range(2, n)),
    }


def _ensure_plotly() -> None:
    if _PLOTLY_IMPORT_ERROR is not None:
        raise RuntimeError(
            "plotly is required for 3D visualisation — run: pip install plotly"
        ) from _PLOTLY_IMPORT_ERROR
