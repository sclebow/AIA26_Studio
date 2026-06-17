"""Site grid and side alignment (Phase 3 of BACKEND_PLAN.md).

Real buildings are not dropped at arbitrary rotations inside a plot — they sit on
a site grid, parallel to a preferred boundary (the street frontage, the longest
edge, the main-road side). This module derives that grid from a **chosen site
side** and exposes the discrete, aligned placement vocabulary the optimizer uses
instead of a free position sweep + 36 free rotations:

* `derive_site_grid` — origin + two axes aligned to a reference side, clipped to
  the buildable zone, with grid lines (for drawing) and grid-node seed points.
* `aligned_orientations` — the discrete orientation set {parallel, perpendicular}
  to the grid (± optional small offsets) — a building can only take these angles.
* `snap_to_grid` / `alignment_score` — snap a point to the lattice; score how
  parallel a footprint's long edge is to a grid axis (1 = perfectly aligned).
* `align_building_to_grid` — place a centred base footprint at a grid node with a
  chosen aligned orientation.
* `corner_interior_angle` / `corner_wing_rotation` — for an L (or other winged
  footprint) tucked into a non-orthogonal site corner: the leaf wing follows the
  *adjacent* side, so its arms spread to the corner's interior angle (obtuse on a
  splayed site) instead of a rigid 90°.

Pure geometry (Shapely in / dict out), deterministic, no LLM or MCP.
"""
from __future__ import annotations

import math
from typing import Any

from shapely import affinity
from shapely.geometry import Polygon

from .view_analysis import _coerce_polygon_2d

DEFAULT_SPACING_M = 10.0
#: Allowed angular slack (deg) when calling a footprint "aligned" to an axis.
ALIGN_TOLERANCE_DEG = 12.0


# ---------------------------------------------------------------------------
# Grid derivation
# ---------------------------------------------------------------------------

def derive_site_grid(
    site_model: dict[str, Any],
    *,
    spacing: float = DEFAULT_SPACING_M,
    alignment_side: int | None = None,
    use_buildable_zone: bool = True,
    margin: float = 0.0,
) -> dict[str, Any]:
    """Build a placement grid aligned to a chosen site side.

    Parameters
    ----------
    site_model:
        Canonical SiteModel (``build_site_model``) — needs ``boundary`` and,
        ideally, ``setbacks.buildable_boundary`` + ``sides``.
    spacing:
        Grid spacing in metres (both axes).
    alignment_side:
        Edge index of the reference side. Default: the **longest** side (the
        sensible fallback before roads land in Phase 2).
    use_buildable_zone:
        Clip the lattice to the setback buildable zone when available.
    margin:
        Extra inset (m) applied to the clip polygon when keeping grid nodes.

    Returns a dict with ``available``, ``origin``, ``u_axis`` (along the side),
    ``v_axis`` (perpendicular, pointing inward), ``angle_deg``, ``spacing``,
    ``alignment_side_index``, ``grid_lines`` (``[[x,y],[x,y]]`` for drawing),
    ``grid_nodes`` (lattice points inside the zone), and ``adjacent_sides``.
    """
    boundary = site_model.get("boundary") if isinstance(site_model, dict) else None
    if not isinstance(boundary, list) or len(boundary) < 3:
        return {"available": False, "reason": "site_model boundary missing"}

    coords = _ring(boundary)
    n = len(coords)

    # Choose the reference side.
    side_idx = alignment_side if alignment_side is not None else _longest_side_index(coords)
    side_idx %= n
    a = coords[side_idx]
    b = coords[(side_idx + 1) % n]
    ux, uy = _unit(a, b)
    if ux == 0.0 and uy == 0.0:
        return {"available": False, "reason": "degenerate reference side"}

    # Inward perpendicular (toward the centroid).
    cx = sum(p[0] for p in coords) / n
    cy = sum(p[1] for p in coords) / n
    vx, vy = -uy, ux
    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    if vx * (cx - mx) + vy * (cy - my) < 0:
        vx, vy = -vx, -vy

    # Clip polygon: the buildable zone (setbacks) when present, else the site.
    clip = _clip_polygon(site_model, boundary, use_buildable_zone)
    if margin > 0:
        clip = clip.buffer(-abs(margin))
        if clip.is_empty:
            clip = _clip_polygon(site_model, boundary, use_buildable_zone)

    # Lattice origin: the corner of the clip's (u, v) projected bounds.
    cpts = _ring(_poly_to_boundary(clip)) if not clip.is_empty else coords
    us = [p[0] * ux + p[1] * uy for p in cpts]
    vs = [p[0] * vx + p[1] * vy for p in cpts]
    u_min, u_max = min(us), max(us)
    v_min, v_max = min(vs), max(vs)
    origin = [round(a[0], 6), round(a[1], 6)]

    grid_nodes: list[list[float]] = []
    nu = max(1, int((u_max - u_min) / spacing) + 1)
    nv = max(1, int((v_max - v_min) / spacing) + 1)
    for i in range(nu + 1):
        for j in range(nv + 1):
            uu = u_min + i * spacing
            vv = v_min + j * spacing
            # Back to world coords (u, v are orthonormal).
            px = uu * ux + vv * vx
            py = uu * uy + vv * vy
            if clip.intersects(_pt(px, py)):  # inside the buildable zone (incl. boundary)
                grid_nodes.append([round(px, 4), round(py, 4)])

    grid_lines = _grid_lines(u_min, u_max, v_min, v_max, spacing, (ux, uy), (vx, vy))

    sides = site_model.get("sides") or []
    adjacent = [(side_idx - 1) % n, (side_idx + 1) % n]
    return {
        "available": True,
        "origin": origin,
        "u_axis": [round(ux, 6), round(uy, 6)],
        "v_axis": [round(vx, 6), round(vy, 6)],
        "angle_deg": round(math.degrees(math.atan2(uy, ux)) % 360.0, 4),
        "spacing": spacing,
        "alignment_side_index": side_idx,
        "alignment_side_label": (sides[side_idx].get("label") if side_idx < len(sides) else f"side_{side_idx}"),
        "grid_nodes": grid_nodes,
        "grid_lines": grid_lines,
        "adjacent_sides": adjacent,
        "node_count": len(grid_nodes),
    }


def aligned_orientations(
    grid: dict[str, Any],
    *,
    include_perpendicular: bool = True,
    offsets_deg: tuple[float, ...] = (),
) -> list[float]:
    """Discrete world rotations (deg) a building may take on this grid.

    Always includes the grid angle (long edge parallel to the chosen side).
    With ``include_perpendicular`` it also includes +90°. ``offsets_deg`` adds
    small ± deviations when a brief explicitly permits looser orientation.
    """
    if not grid.get("available"):
        return [0.0]
    base = float(grid["angle_deg"])
    angles = [base]
    if include_perpendicular:
        angles.append((base + 90.0) % 360.0)
    out: list[float] = []
    for ang in angles:
        out.append(ang % 360.0)
        for off in offsets_deg:
            out.append((ang + off) % 360.0)
            out.append((ang - off) % 360.0)
    # De-duplicate while preserving order.
    seen: set[float] = set()
    uniq: list[float] = []
    for ang in out:
        key = round(ang, 4)
        if key not in seen:
            seen.add(key)
            uniq.append(round(ang, 4))
    return uniq


def snap_to_grid(point: list[float], grid: dict[str, Any]) -> list[float]:
    """Return the grid node nearest to ``point`` (falls back to the point)."""
    nodes = grid.get("grid_nodes") or []
    if not nodes:
        return [float(point[0]), float(point[1])]
    px, py = float(point[0]), float(point[1])
    return min(nodes, key=lambda q: (q[0] - px) ** 2 + (q[1] - py) ** 2)


def alignment_score(building_boundary: list[list[float]], grid: dict[str, Any]) -> float:
    """0–1: how parallel the footprint's longest edge is to a grid axis.

    1.0 = the long edge is exactly parallel (or perpendicular) to the chosen
    side; it falls to 0 at ``ALIGN_TOLERANCE_DEG`` * (some slack) off-axis.
    """
    if not grid.get("available"):
        return 0.0
    edge = _longest_edge_angle(building_boundary)
    grid_ang = math.radians(float(grid["angle_deg"]))
    # Deviation to the nearest of the two orthogonal axes, folded into [0, 45].
    diff = abs(_wrap_angle(edge - grid_ang))
    diff = min(diff, abs(_wrap_angle(edge - (grid_ang + math.pi / 2))))
    dev_deg = math.degrees(diff)
    return float(max(0.0, 1.0 - dev_deg / 45.0))


def align_building_to_grid(
    base_boundary: list[list[float]],
    grid: dict[str, Any],
    node_xy: list[float],
    orientation_deg: float,
) -> list[list[float]]:
    """Rotate a centred base footprint to ``orientation_deg`` and drop it at ``node_xy``."""
    poly = _coerce_polygon_2d(base_boundary)
    c = poly.centroid
    poly = affinity.translate(poly, xoff=-c.x, yoff=-c.y)
    poly = affinity.rotate(poly, float(orientation_deg), origin=(0.0, 0.0), use_radians=False)
    poly = affinity.translate(poly, xoff=float(node_xy[0]), yoff=float(node_xy[1]))
    return _poly_to_boundary(poly)


# ---------------------------------------------------------------------------
# Non-orthogonal corners (obtuse / splayed footprints)
# ---------------------------------------------------------------------------

def corner_interior_angle(site_model: dict[str, Any], corner_index: int) -> float | None:
    """Interior angle (deg) at site corner ``corner_index`` between its two sides."""
    boundary = site_model.get("boundary") if isinstance(site_model, dict) else None
    if not isinstance(boundary, list) or len(boundary) < 3:
        return None
    coords = _ring(boundary)
    n = len(coords)
    i = corner_index % n
    prev_pt = coords[(i - 1) % n]
    cur = coords[i]
    nxt = coords[(i + 1) % n]
    ax, ay = prev_pt[0] - cur[0], prev_pt[1] - cur[1]
    bx, by = nxt[0] - cur[0], nxt[1] - cur[1]
    da = math.hypot(ax, ay)
    db = math.hypot(bx, by)
    if da < 1e-9 or db < 1e-9:
        return None
    cosang = max(-1.0, min(1.0, (ax * bx + ay * by) / (da * db)))
    return round(math.degrees(math.acos(cosang)), 4)


def corner_wing_rotation(site_model: dict[str, Any], alignment_side_index: int) -> float:
    """Leaf-wing rotation (deg) so an L's free arm follows the *adjacent* side.

    When the building's main wing aligns to ``alignment_side_index`` and the next
    side meets it at an interior angle θ, the free wing should rotate by
    ``θ - 90`` so its arms span θ (obtuse on a splayed corner) instead of a rigid
    right angle. Returns 0 on a square corner.
    """
    n = len(_ring(site_model.get("boundary", [])))
    if n < 3:
        return 0.0
    corner = (alignment_side_index + 1) % n  # shared corner of side i and i+1
    theta = corner_interior_angle(site_model, corner)
    if theta is None:
        return 0.0
    return round(theta - 90.0, 4)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ring(boundary: list[list[float]]) -> list[tuple[float, float]]:
    pts = [(float(p[0]), float(p[1])) for p in boundary]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def _unit(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return 0.0, 0.0
    return dx / L, dy / L


def _longest_side_index(coords: list[tuple[float, float]]) -> int:
    n = len(coords)
    best_i, best_len = 0, -1.0
    for i in range(n):
        a, b = coords[i], coords[(i + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L > best_len:
            best_len, best_i = L, i
    return best_i


def _clip_polygon(site_model: dict[str, Any], boundary: list[list[float]], use_buildable: bool) -> Polygon:
    if use_buildable:
        setbacks = site_model.get("setbacks") or {}
        bz = setbacks.get("buildable_boundary")
        if isinstance(bz, list) and len(bz) >= 3:
            try:
                return _coerce_polygon_2d(bz)
            except Exception:
                pass
    return _coerce_polygon_2d(boundary)


def _grid_lines(
    u_min: float, u_max: float, v_min: float, v_max: float, spacing: float,
    u_axis: tuple[float, float], v_axis: tuple[float, float],
) -> list[list[list[float]]]:
    ux, uy = u_axis
    vx, vy = v_axis
    lines: list[list[list[float]]] = []

    def world(uu: float, vv: float) -> list[float]:
        return [round(uu * ux + vv * vx, 4), round(uu * uy + vv * vy, 4)]

    nu = int((u_max - u_min) / spacing) + 1
    nv = int((v_max - v_min) / spacing) + 1
    for i in range(nu + 1):  # lines parallel to v (constant u)
        uu = u_min + i * spacing
        lines.append([world(uu, v_min), world(uu, v_max)])
    for j in range(nv + 1):  # lines parallel to u (constant v)
        vv = v_min + j * spacing
        lines.append([world(u_min, vv), world(u_max, vv)])
    return lines


def _poly_to_boundary(poly: Polygon) -> list[list[float]]:
    return [[round(float(x), 6), round(float(y), 6), 0.0] for x, y in poly.exterior.coords]


def _pt(x: float, y: float):
    from shapely.geometry import Point
    return Point(x, y)


def _longest_edge_angle(boundary: list[list[float]]) -> float:
    coords = _ring(boundary)
    n = len(coords)
    best_ang, best_len = 0.0, -1.0
    for i in range(n):
        a, b = coords[i], coords[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L > best_len:
            best_len, best_ang = L, math.atan2(dy, dx)
    return best_ang


def _wrap_angle(a: float) -> float:
    """Wrap to (-pi/2, pi/2] — orientation is undirected (a line, not a ray)."""
    while a > math.pi / 2:
        a -= math.pi
    while a <= -math.pi / 2:
        a += math.pi
    return a
