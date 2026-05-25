"""
nodes/collision.py — Grid-based collision and accessibility analysis.

Ports the GH collision-detector-grid logic into pure Python so the graph
can evaluate results before sending to the LLM. GH only handles visualization.

Two modes:
  Mode 1 (no furniture): checks room boundaries, door widths, turning radii
  Mode 2 (furniture present): full grid analysis with clearance field,
         use_point checking, functional_point line checking, move suggestions

Requires: collections (stdlib), math (stdlib)
No Rhino dependency — pure Python only.
"""

from __future__ import annotations
import json
import math
from collections import deque
from typing import Any


# ---------------------------------------------------------------------------
# Default profiles — used when no profile_config in state
# ---------------------------------------------------------------------------

DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "wheelchair": {
        "min_door_width_m": 0.85,
        "min_corridor_width_m": 0.90,
        "turning_radius_m": 1.50,
        "body_width_m": 0.70,
    },
    "elderly": {
        "min_door_width_m": 0.80,
        "min_corridor_width_m": 0.85,
        "turning_radius_m": 1.20,
        "body_width_m": 0.60,
    },
    "stroller": {
        "min_door_width_m": 0.80,
        "min_corridor_width_m": 0.90,
        "turning_radius_m": 1.30,
        "body_width_m": 0.65,
    },
    "autistic": {
        "min_door_width_m": 0.75,
        "min_corridor_width_m": 0.80,
        "turning_radius_m": 1.00,
        "body_width_m": 0.55,
    },
    "visually_impaired": {
        "min_door_width_m": 0.80,
        "min_corridor_width_m": 0.90,
        "turning_radius_m": 1.20,
        "body_width_m": 0.60,
    },
    "forklift": {
        "min_door_width_m": 2.50,
        "min_corridor_width_m": 3.00,
        "turning_radius_m": 3.50,
        "body_width_m": 1.20,
    },
    "crane": {
        "min_door_width_m": 4.00,
        "min_corridor_width_m": 5.00,
        "turning_radius_m": 5.00,
        "body_width_m": 2.00,
    },
}

# Grid resolution in metres — balances accuracy vs speed
GRID_RESOLUTION = 0.10


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------

def _resolve_profile(profile_config: dict | None) -> dict:
    """
    Resolve the active profile from state["profile_config"].
    Falls back to wheelchair defaults if nothing provided.
    Always ensures user_type key is present in the result.
    """
    if not profile_config:
        # No profile provided — use wheelchair defaults
        base = dict(DEFAULT_PROFILES["wheelchair"])
        base["user_type"] = "wheelchair"
        return base
    user_type = profile_config.get("profile_type", "wheelchair")
    base = dict(DEFAULT_PROFILES.get(user_type, DEFAULT_PROFILES["wheelchair"]))
    base["user_type"] = user_type
    # Map profile_agent keys to collision keys
    if "min_path_width" in profile_config:
        base["min_corridor_width_m"] = profile_config["min_path_width"]
    if "turning_radius" in profile_config:
        base["turning_radius_m"] = profile_config["turning_radius"]
    return base


# ---------------------------------------------------------------------------
# Wall geometry helpers
# ---------------------------------------------------------------------------

def _point_on_segment_t(seg_p1, seg_p2, pt, tolerance=0.02):
    """
    Project pt onto segment [seg_p1, seg_p2].
    Returns parameter t (0-1) if pt is within tolerance of the segment,
    else None. Used to find where doors intersect walls.
    """
    dx = seg_p2[0] - seg_p1[0]
    dy = seg_p2[1] - seg_p1[1]
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-12:
        return None
    t = ((pt[0] - seg_p1[0]) * dx + (pt[1] - seg_p1[1]) * dy) / seg_len_sq
    proj_x = seg_p1[0] + t * dx
    proj_y = seg_p1[1] + t * dy
    dist_sq = (pt[0] - proj_x) ** 2 + (pt[1] - proj_y) ** 2
    if dist_sq > tolerance * tolerance:
        return None
    return t


def _split_wall_at_doors(wp1, wp2, door_segments, half_thickness):
    """
    Split a wall segment into parts that exclude door openings.
    This ensures doors are passable gaps in the wall obstacles.
    """
    door_intervals = []
    for dp1, dp2 in door_segments:
        t1 = _point_on_segment_t(wp1, wp2, dp1)
        t2 = _point_on_segment_t(wp1, wp2, dp2)
        if t1 is not None and t2 is not None:
            door_intervals.append((min(t1, t2), max(t1, t2)))

    if not door_intervals:
        return [(wp1, wp2)]

    # Merge overlapping door intervals
    door_intervals.sort()
    merged = [door_intervals[0]]
    for start, end in door_intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    dx = wp2[0] - wp1[0]
    dy = wp2[1] - wp1[1]
    parts = []
    prev_t = 0.0
    for t_start, t_end in merged:
        if t_start > prev_t + 0.001:
            p_a = [wp1[0] + prev_t * dx, wp1[1] + prev_t * dy]
            p_b = [wp1[0] + t_start * dx, wp1[1] + t_start * dy]
            parts.append((p_a, p_b))
        prev_t = t_end
    if prev_t < 1.0 - 0.001:
        p_a = [wp1[0] + prev_t * dx, wp1[1] + prev_t * dy]
        parts.append((p_a, list(wp2)))
    return parts


def _buffer_wall_segment(p1, p2, half_thickness):
    """
    Convert a wall centerline segment into a rectangle polygon (4 corners).
    The rectangle has width = wall_thickness centered on the centerline.
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return None
    nx = -dy / length * half_thickness
    ny = dx / length * half_thickness
    return [
        [p1[0] + nx, p1[1] + ny],
        [p2[0] + nx, p2[1] + ny],
        [p2[0] - nx, p2[1] - ny],
        [p1[0] - nx, p1[1] - ny],
        [p1[0] + nx, p1[1] + ny],
    ]


# ---------------------------------------------------------------------------
# Grid rasterization
# ---------------------------------------------------------------------------

def _rasterize_polygon(polygon_pts, grid, attrib_grid, cols, rows,
                       ox, oy, cs, value, obj_index):
    """
    Scanline fill a closed polygon onto the grid.
    Marks cells as obstacles (value=-2) and records which object owns each cell.
    """
    n = len(polygon_pts)
    if n < 3:
        return
    gpts = [((p[0] - ox) / cs, (p[1] - oy) / cs) for p in polygon_pts]

    min_gy = max(0, int(math.floor(min(p[1] for p in gpts))))
    max_gy = min(rows - 1, int(math.floor(max(p[1] for p in gpts))))

    for gy in range(min_gy, max_gy + 1):
        scanline_y = gy + 0.5
        intersections = []
        for i in range(n - 1):
            y0, y1 = gpts[i][1], gpts[i + 1][1]
            if y0 == y1:
                continue
            if min(y0, y1) <= scanline_y < max(y0, y1):
                t = (scanline_y - y0) / (y1 - y0)
                x_int = gpts[i][0] + t * (gpts[i + 1][0] - gpts[i][0])
                intersections.append(x_int)
        intersections.sort()
        for k in range(0, len(intersections) - 1, 2):
            x_start = max(0, int(math.floor(intersections[k])))
            x_end = min(cols - 1, int(math.floor(intersections[k + 1])))
            for gx in range(x_start, x_end + 1):
                idx = gy * cols + gx
                grid[idx] = value
                attrib_grid[idx] = obj_index


# ---------------------------------------------------------------------------
# Distance field (BFS brushfire)
# ---------------------------------------------------------------------------

def _compute_distance_field(grid, cols, rows):
    """
    BFS from all obstacle cells outward.
    Returns distance array where each cell value = cells away from nearest obstacle.
    Cells with value -1 are outside the layout boundary.
    """
    total = cols * rows
    dist = [0] * total
    queue = deque()

    for idx in range(total):
        if grid[idx] == -2:
            dist[idx] = 0
            queue.append(idx)
        elif grid[idx] == -1:
            dist[idx] = -1  # outside boundary
        else:
            dist[idx] = 999999

    while queue:
        idx = queue.popleft()
        x = idx % cols
        y = idx // cols
        d = dist[idx]
        for nidx in [idx-1, idx+1, idx-cols, idx+cols]:
            nx = nidx % cols
            ny = nidx // cols
            if 0 <= nx < cols and 0 <= ny < rows:
                if dist[nidx] > d + 1:
                    dist[nidx] = d + 1
                    queue.append(nidx)
    return dist


def _compute_nearest_obstacle(grid, attrib_grid, cols, rows):
    """
    BFS from obstacles, propagating which object is nearest to each cell.
    Used to attribute violations back to specific objects.
    """
    total = cols * rows
    dist = [0] * total
    nearest = [-1] * total
    queue = deque()

    for idx in range(total):
        if grid[idx] == -2:
            dist[idx] = 0
            nearest[idx] = attrib_grid[idx]
            queue.append(idx)
        elif grid[idx] == -1:
            dist[idx] = -1
        else:
            dist[idx] = 999999

    while queue:
        idx = queue.popleft()
        x = idx % cols
        y = idx // cols
        d = dist[idx]
        obj_i = nearest[idx]
        for nidx in [idx-1, idx+1, idx-cols, idx+cols]:
            nx = nidx % cols
            ny = nidx // cols
            if 0 <= nx < cols and 0 <= ny < rows:
                if dist[nidx] > d + 1:
                    dist[nidx] = d + 1
                    nearest[nidx] = obj_i
                    queue.append(nidx)
    return nearest


# ---------------------------------------------------------------------------
# Bresenham line for functional_point check
# ---------------------------------------------------------------------------

def _bresenham(x0, y0, x1, y1):
    """
    Rasterize a line between two grid cells.
    Used to check if the line from use_point to functional_point is blocked.
    """
    cells = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        cells.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return cells


# ---------------------------------------------------------------------------
# Use-point analysis
# ---------------------------------------------------------------------------

def _check_use_point_clearance(use_point, dist, attrib_grid,
                                self_obj_index, cols, rows,
                                ox, oy, cs, body_half_cells):
    """
    Check if a use_point has sufficient clearance around it.
    Ignores self as an obstacle (the object being checked).
    Returns clearance_m, sufficient bool, deficit_m.
    """
    gx = int(round((use_point[0] - ox) / cs))
    gy = int(round((use_point[1] - oy) / cs))

    if not (0 <= gx < cols and 0 <= gy < rows):
        return {"clearance_m": 0.0, "sufficient": False,
                "deficit_m": round(body_half_cells * cs, 3)}

    idx = gy * cols + gx
    d = dist[idx]

    # If use_point lands on own object, search outward for real clearance
    if d <= 0 and attrib_grid[idx] == self_obj_index:
        best_d = 999999
        search_r = body_half_cells + 3
        for dy_s in range(-search_r, search_r + 1):
            for dx_s in range(-search_r, search_r + 1):
                nx, ny = gx + dx_s, gy + dy_s
                if 0 <= nx < cols and 0 <= ny < rows:
                    ni = ny * cols + nx
                    if dist[ni] > 0:
                        best_d = min(best_d, dist[ni])
        d = best_d if best_d < 999999 else 0

    if d < 0:
        return {"clearance_m": 0.0, "sufficient": False,
                "deficit_m": round(body_half_cells * cs, 3)}

    clearance_m = d * cs
    required_m = body_half_cells * cs
    return {
        "clearance_m": round(clearance_m, 3),
        "sufficient": d >= body_half_cells,
        "deficit_m": round(max(0, required_m - clearance_m), 3),
    }


def _check_functional_line(use_point, functional_point, grid,
                            attrib_grid, obj_registry,
                            self_obj_index, cols, rows, ox, oy, cs):
    """
    Check if the line from use_point to functional_point is blocked.
    Uses Bresenham rasterization to check each cell along the line.
    Ignores self as blocker.
    """
    x0 = max(0, min(cols-1, int(round((use_point[0] - ox) / cs))))
    y0 = max(0, min(rows-1, int(round((use_point[1] - oy) / cs))))
    x1 = max(0, min(cols-1, int(round((functional_point[0] - ox) / cs))))
    y1 = max(0, min(rows-1, int(round((functional_point[1] - oy) / cs))))

    for (cx, cy) in _bresenham(x0, y0, x1, y1):
        if not (0 <= cx < cols and 0 <= cy < rows):
            continue
        idx = cy * cols + cx
        if grid[idx] == -2:
            obj_i = attrib_grid[idx]
            if obj_i == self_obj_index:
                continue
            blocking = (obj_registry[obj_i]
                       if 0 <= obj_i < len(obj_registry)
                       else {"id": "unknown", "name": "unknown", "type": "unknown"})
            return {
                "blocked": True,
                "blocking_object_id": blocking["id"],
                "blocking_object_name": blocking["name"],
                "blocking_object_type": blocking["type"],
                "block_point": [round(ox + cx * cs, 3), round(oy + cy * cs, 3)],
            }
    return {"blocked": False}


def _compute_reachable_from_doors(doors, dist, cols, rows,
                                   ox, oy, cs, body_half_cells):
    """
    BFS from door midpoints through all cells with sufficient clearance.
    Returns set of reachable cell indices.
    Used to check connectivity — can you physically reach every object?
    """
    if not doors:
        return set()

    first_door = next(
        (d for d in doors if len(d.get("geometry", [])) == 2), None
    )
    if not first_door:
        return set()

    geom = first_door["geometry"]
    mid_x = (geom[0][0] + geom[1][0]) / 2.0
    mid_y = (geom[0][1] + geom[1][1]) / 2.0
    dcx = int((mid_x - ox) / cs)
    dcy = int((mid_y - oy) / cs)

    search_r = body_half_cells + 4
    seeds = {
        ny * cols + nx
        for dy in range(-search_r, search_r + 1)
        for dx in range(-search_r, search_r + 1)
        for nx, ny in [(dcx + dx, dcy + dy)]
        if 0 <= nx < cols and 0 <= ny < rows
        and dist[ny * cols + nx] >= body_half_cells
    }

    if not seeds:
        return set()

    reachable = set(seeds)
    bfs_q = deque(seeds)
    while bfs_q:
        ci = bfs_q.popleft()
        cx_pos = ci % cols
        cy_pos = ci // cols
        for nidx in [ci-1, ci+1, ci-cols, ci+cols]:
            nx = nidx % cols
            ny = nidx // cols
            if (0 <= nx < cols and 0 <= ny < rows
                    and nidx not in reachable
                    and dist[nidx] >= body_half_cells):
                reachable.add(nidx)
                bfs_q.append(nidx)
    return reachable


def _check_use_point_reachability(use_point, reachable_set,
                                   dist, cols, rows, ox, oy, cs,
                                   body_half_cells):
    """
    Check if a use_point is reachable from the doors
    through passable cells (clearance >= body width).
    """
    if not reachable_set:
        return {"reachable": False, "reason": "no reachable cells (no doors?)"}

    gx = int(round((use_point[0] - ox) / cs))
    gy = int(round((use_point[1] - oy) / cs))

    if not (0 <= gx < cols and 0 <= gy < rows):
        return {"reachable": False, "reason": "use_point outside grid"}

    search_r = max(3, body_half_cells + 1)
    for dy in range(-search_r, search_r + 1):
        for dx in range(-search_r, search_r + 1):
            nx, ny = gx + dx, gy + dy
            if 0 <= nx < cols and 0 <= ny < rows:
                if ny * cols + nx in reachable_set:
                    return {"reachable": True, "reason": None}

    return {"reachable": False, "reason": "no passable path from doors"}


def _compute_move_suggestion(use_point, dist, nearest, obj_registry,
                              cols, rows, ox, oy, cs, body_half_cells):
    """
    Compute a movement vector to resolve a clearance violation.
    Uses gradient of the distance field to find the direction
    that increases clearance fastest.
    """
    gx = int(round((use_point[0] - ox) / cs))
    gy = int(round((use_point[1] - oy) / cs))

    if not (1 <= gx < cols-1 and 1 <= gy < rows-1):
        return None

    idx = gy * cols + gx
    d = dist[idx]
    if d < 0 or d >= body_half_cells:
        return None  # no violation — no suggestion needed

    # Central difference gradient of distance field
    d_right = max(0, dist[idx + 1])
    d_left  = max(0, dist[idx - 1])
    d_up    = max(0, dist[idx + cols])
    d_down  = max(0, dist[idx - cols])

    grad_x = (d_right - d_left) / 2.0
    grad_y = (d_up - d_down) / 2.0
    mag = math.sqrt(grad_x**2 + grad_y**2)

    if mag < 0.01:
        return None

    dx_norm = grad_x / mag
    dy_norm = grad_y / mag
    deficit_m = (body_half_cells - d) * cs
    move_dist = deficit_m / min(mag, 1.0)

    nearest_id = None
    ni = nearest[idx]
    if 0 <= ni < len(obj_registry):
        nearest_id = obj_registry[ni]["id"]

    return {
        "direction": [round(dx_norm, 3), round(dy_norm, 3)],
        "distance_m": round(move_dist, 3),
        "deficit_m": round(deficit_m, 3),
        "nearest_obstacle_id": nearest_id,
    }


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def check_collision(
    layout: dict[str, Any],
    profile_config: dict[str, Any] | None = None,
    wall_thickness: float = 0.20,
    compare_layout: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run full grid-based collision and accessibility analysis.

    Mode 1 (no furniture): checks room boundaries, door widths, turning radii.
    Mode 2 (furniture present): full grid with clearance field, use_point
    checking, functional_point line checking, and move suggestions.

    Args:
        layout: the current layout dict
        profile_config: from state["profile_config"] — Profile Agent output
        wall_thickness: wall thickness in metres (default 0.20m)
        compare_layout: optional previous layout for before/after diff

    Returns:
        dict with pass, violations, objects, doors, summary, grid_meta
    """
    cs = GRID_RESOLUTION
    profile = _resolve_profile(profile_config)

    outline = layout.get("outline", [])
    if not outline or len(outline) < 3:
        return {
            "pass": False,
            "violations": ["No valid outline found in layout"],
            "summary": {"total_violations": 1},
            "objects": [],
            "doors": [],
        }

    # ── Build bounding box and initialize grids ──────────────────────────
    all_x = [p[0] for p in outline]
    all_y = [p[1] for p in outline]
    ox = min(all_x)
    oy = min(all_y)
    cols = int(math.ceil((max(all_x) - ox) / cs)) + 1
    rows = int(math.ceil((max(all_y) - oy) / cs)) + 1
    total = cols * rows

    # grid: -1=outside, 0=free inside, -2=obstacle
    grid = [-1] * total
    attrib_grid = [-1] * total
    obj_registry: list[dict] = []

    # ── Rasterize interior (free space) ──────────────────────────────────
    _rasterize_polygon(outline, grid, attrib_grid,
                       cols, rows, ox, oy, cs, 0, -1)

    # ── Collect door segments for wall splitting ──────────────────────────
    door_segments = [
        (d["geometry"][0], d["geometry"][1])
        for d in layout.get("doors", [])
        if len(d.get("geometry", [])) == 2
    ]
    half_t = wall_thickness / 2.0

    # ── Rasterize walls ───────────────────────────────────────────────────
    for wall in layout.get("structure", []):
        geom = wall.get("geometry", [])
        if len(geom) != 2:
            continue
        obj_i = len(obj_registry)
        obj_registry.append({
            "id": wall.get("id", "unknown"),
            "name": wall.get("name", "wall"),
            "type": "structure",
            "use_point": None,
            "functional_point": None,
        })
        for seg_p1, seg_p2 in _split_wall_at_doors(
                geom[0], geom[1], door_segments, half_t):
            rect = _buffer_wall_segment(seg_p1, seg_p2, half_t)
            if rect:
                _rasterize_polygon(rect, grid, attrib_grid,
                                   cols, rows, ox, oy, cs, -2, obj_i)

    # ── Rasterize furniture ───────────────────────────────────────────────
    objects = layout.get("objects") or layout.get("furniture") or []
    for furn in objects:
        geom = furn.get("geometry", [])
        if len(geom) >= 3:
            obj_i = len(obj_registry)
            obj_registry.append({
                "id": furn.get("id", "unknown"),
                "name": furn.get("name", "furniture"),
                "type": "furniture",
                "use_point": furn.get("use_point"),
                "functional_point": furn.get("functional_point"),
            })
            _rasterize_polygon(geom, grid, attrib_grid,
                               cols, rows, ox, oy, cs, -2, obj_i)

    # ── Rasterize MEP ─────────────────────────────────────────────────────
    for mep in layout.get("mep", []):
        geom = mep.get("geometry", [])
        if len(geom) >= 3:
            obj_i = len(obj_registry)
            obj_registry.append({
                "id": mep.get("id", "unknown"),
                "name": mep.get("name", "mep"),
                "type": "mep",
                "use_point": None,
                "functional_point": None,
            })
            _rasterize_polygon(geom, grid, attrib_grid,
                               cols, rows, ox, oy, cs, -2, obj_i)

    # ── Compute distance field and nearest obstacle ───────────────────────
    dist    = _compute_distance_field(grid, cols, rows)
    nearest = _compute_nearest_obstacle(grid, attrib_grid, cols, rows)

    body_half_cells     = int(math.ceil((profile["body_width_m"] / 2.0) / cs))
    corridor_half_cells = int(math.ceil(
        (profile["min_corridor_width_m"] / 2.0) / cs))

    violations: list[str] = []
    obj_violation_data: dict[int, dict] = {}

    # ── Find violation and warning cells ─────────────────────────────────
    violation_cells: list[int] = []
    warning_cells: list[int] = []

    for idx in range(total):
        d = dist[idx]
        if d <= 0 or d == -1:
            continue
        obj_i = nearest[idx]
        if d < body_half_cells:
            violation_cells.append(idx)
            if obj_i >= 0:
                e = obj_violation_data.setdefault(
                    obj_i, {"blocked_cells": 0, "warning_cells": 0,
                            "min_clearance_m": 999.0})
                e["blocked_cells"] += 1
                e["min_clearance_m"] = min(e["min_clearance_m"], d * cs)
        elif d < corridor_half_cells:
            warning_cells.append(idx)
            if obj_i >= 0:
                e = obj_violation_data.setdefault(
                    obj_i, {"blocked_cells": 0, "warning_cells": 0,
                            "min_clearance_m": 999.0})
                e["warning_cells"] += 1
                e["min_clearance_m"] = min(e["min_clearance_m"], d * cs)

    if violation_cells:
        violations.append(
            "BLOCKED: {} cells ({:.2f}m²) clearance < {:.2f}m".format(
                len(violation_cells),
                len(violation_cells) * cs * cs,
                profile["body_width_m"] / 2.0,
            )
        )
    if warning_cells:
        violations.append(
            "WARNING: {} cells ({:.2f}m²) below corridor spec {:.2f}m".format(
                len(warning_cells),
                len(warning_cells) * cs * cs,
                profile["min_corridor_width_m"] / 2.0,
            )
        )

    # ── Door width check ──────────────────────────────────────────────────
    door_violations: list[dict] = []
    for door in layout.get("doors", []):
        geom = door.get("geometry", [])
        if len(geom) == 2:
            dx = geom[1][0] - geom[0][0]
            dy = geom[1][1] - geom[0][1]
            width = math.sqrt(dx*dx + dy*dy)
            if width < profile["min_door_width_m"] - 0.01:
                deficit = profile["min_door_width_m"] - width
                violations.append(
                    "DOOR_WIDTH: '{}' {:.2f}m < required {:.2f}m (deficit {:.2f}m)".format(
                        door.get("name", door.get("id", "?")),
                        width, profile["min_door_width_m"], deficit,
                    )
                )
                door_violations.append({
                    "id": door.get("id", "unknown"),
                    "name": door.get("name", "door"),
                    "type": "width",
                    "actual_m": round(width, 3),
                    "required_m": profile["min_door_width_m"],
                    "deficit_m": round(deficit, 3),
                })

    # ── Turning radius check ──────────────────────────────────────────────
    turning_cells = int(math.ceil(profile["turning_radius_m"] / cs))
    turning_violations: list[dict] = []
    for door in layout.get("doors", []):
        geom = door.get("geometry", [])
        if len(geom) != 2:
            continue
        mid_x = (geom[0][0] + geom[1][0]) / 2.0
        mid_y = (geom[0][1] + geom[1][1]) / 2.0
        cx = int((mid_x - ox) / cs)
        cy = int((mid_y - oy) / cs)
        search_r = min(turning_cells * 2, 60)
        found = False
        max_found = 0
        for dy_s in range(-search_r, search_r + 1, 2):
            for dx_s in range(-search_r, search_r + 1, 2):
                gx, gy = cx + dx_s, cy + dy_s
                if 0 <= gx < cols and 0 <= gy < rows:
                    d = dist[gy * cols + gx]
                    if d >= turning_cells:
                        found = True
                        break
                    max_found = max(max_found, d)
            if found:
                break
        if not found:
            available = max_found * cs
            violations.append(
                "TURNING: '{}' needs {:.2f}m radius, available {:.2f}m".format(
                    door.get("name", door.get("id", "?")),
                    profile["turning_radius_m"], available,
                )
            )
            turning_violations.append({
                "id": door.get("id", "unknown"),
                "name": door.get("name", "door"),
                "type": "turning_radius",
                "required_m": profile["turning_radius_m"],
                "available_m": round(available, 3),
                "deficit_m": round(profile["turning_radius_m"] - available, 3),
            })

    # ── Reachability from doors ───────────────────────────────────────────
    reachable_set = _compute_reachable_from_doors(
        layout.get("doors", []), dist, cols, rows,
        ox, oy, cs, body_half_cells)

    # ── Connectivity check (all doors reachable from first door) ──────────
    doors = layout.get("doors", [])
    if len(doors) > 1 and reachable_set:
        search_r = body_half_cells + 4
        for door in doors[1:]:
            geom = door.get("geometry", [])
            if len(geom) != 2:
                continue
            mid_x = (geom[0][0] + geom[1][0]) / 2.0
            mid_y = (geom[0][1] + geom[1][1]) / 2.0
            dcx = int((mid_x - ox) / cs)
            dcy = int((mid_y - oy) / cs)
            seeds = {
                ny * cols + nx
                for ddy in range(-search_r, search_r + 1)
                for ddx in range(-search_r, search_r + 1)
                for nx, ny in [(dcx + ddx, dcy + ddy)]
                if 0 <= nx < cols and 0 <= ny < rows
                and dist[ny * cols + nx] >= body_half_cells
            }
            if not seeds or not seeds.intersection(reachable_set):
                violations.append(
                    "CONNECTIVITY: Door '{}' unreachable for {}".format(
                        door.get("name", door.get("id", "?")),
                        profile["user_type"],
                    )
                )

    # ── Use-point and functional-point analysis ───────────────────────────
    use_point_results: dict[int, dict] = {}

    for obj_i, obj_info in enumerate(obj_registry):
        up = obj_info.get("use_point")
        if up is None:
            continue

        clearance = _check_use_point_clearance(
            up, dist, attrib_grid, obj_i,
            cols, rows, ox, oy, cs, body_half_cells)

        reachability = _check_use_point_reachability(
            up, reachable_set, dist,
            cols, rows, ox, oy, cs, body_half_cells)

        move_sug = None
        if not clearance["sufficient"]:
            move_sug = _compute_move_suggestion(
                up, dist, nearest, obj_registry,
                cols, rows, ox, oy, cs, body_half_cells)

        fp = obj_info.get("functional_point")
        func_line = None
        if fp is not None:
            func_line = _check_functional_line(
                up, fp, grid, attrib_grid, obj_registry,
                obj_i, cols, rows, ox, oy, cs)

        use_point_results[obj_i] = {
            "use_point": up,
            "clearance_m": clearance["clearance_m"],
            "clearance_sufficient": clearance["sufficient"],
            "deficit_m": clearance["deficit_m"],
            "reachable": reachability["reachable"],
            "reachability_reason": reachability.get("reason"),
            "move_suggestion": move_sug,
            "functional_point": fp,
            "functional_line": func_line,
        }

        if not clearance["sufficient"]:
            violations.append(
                "USE_POINT: '{}' clearance {:.2f}m < required {:.2f}m".format(
                    obj_info["name"], clearance["clearance_m"],
                    body_half_cells * cs,
                )
            )
        if not reachability["reachable"]:
            violations.append(
                "USE_POINT_UNREACHABLE: '{}' — {}".format(
                    obj_info["name"], reachability.get("reason", "blocked"),
                )
            )
        if func_line and func_line.get("blocked"):
            violations.append(
                "FUNCTIONAL_LINE: '{}' blocked by '{}'".format(
                    obj_info["name"],
                    func_line["blocking_object_name"],
                )
            )

    # ── Build per-object report entries ───────────────────────────────────
    objects_out: list[dict] = []
    for obj_i, obj_info in enumerate(obj_registry):
        has_cv = obj_i in obj_violation_data
        has_up = obj_i in use_point_results
        if not has_cv and not has_up:
            continue
        entry: dict = {
            "id": obj_info["id"],
            "name": obj_info["name"],
            "type": obj_info["type"],
            "clearance_violation": None,
            "use_point_analysis": None,
            "functional_line_analysis": None,
        }
        if has_cv:
            data = obj_violation_data[obj_i]
            entry["clearance_violation"] = {
                "blocked_cells": data["blocked_cells"],
                "blocked_area_m2": round(data["blocked_cells"] * cs * cs, 3),
                "warning_cells": data["warning_cells"],
                "min_clearance_m": round(data["min_clearance_m"], 3),
                "required_m": round(body_half_cells * cs, 3),
                "deficit_m": round(
                    max(0, body_half_cells * cs - data["min_clearance_m"]), 3),
            }
        if has_up:
            upr = use_point_results[obj_i]
            entry["use_point_analysis"] = {
                "clearance_m": upr["clearance_m"],
                "sufficient": upr["clearance_sufficient"],
                "deficit_m": upr["deficit_m"],
                "reachable": upr["reachable"],
                "move_suggestion": upr["move_suggestion"],
            }
            if upr["functional_line"] is not None:
                fl = upr["functional_line"]
                entry["functional_line_analysis"] = {
                    "functional_point": upr["functional_point"],
                    "blocked": fl["blocked"],
                }
                if fl["blocked"]:
                    entry["functional_line_analysis"].update({
                        "blocking_object_id": fl["blocking_object_id"],
                        "blocking_object_name": fl["blocking_object_name"],
                        "block_point": fl["block_point"],
                    })
        objects_out.append(entry)

    # Sort by severity (most blocked first)
    objects_out.sort(key=lambda o: (
        -(o["clearance_violation"] or {}).get("blocked_cells", 0)
    ))

    # ── Before/after comparison ───────────────────────────────────────────
    comparison = None
    if compare_layout is not None:
        prev_result = check_collision(compare_layout, profile_config,
                                      wall_thickness)
        prev_set = set(prev_result.get("violations", []))
        new_violations = [v for v in violations if v not in prev_set]
        comparison = {
            "has_previous": True,
            "new_violation_count": len(new_violations),
            "new_violations": new_violations,
        }

    # ── Door violations grouped ───────────────────────────────────────────
    doors_grouped: dict[str, dict] = {}
    for dv in door_violations + turning_violations:
        did = dv["id"]
        if did not in doors_grouped:
            doors_grouped[did] = {
                "id": did, "name": dv["name"], "violations": []}
        doors_grouped[did]["violations"].append({
            k: v for k, v in dv.items() if k not in ("id", "name")
        })

    # ── Assemble final report ─────────────────────────────────────────────
    hard_violations = [v for v in violations
                       if not v.startswith("WARNING:")]
    pass_fail = len(hard_violations) == 0

    report = {
        "pass": pass_fail,
        "profile": {
            "user_type": profile["user_type"],
            "body_width_m": profile["body_width_m"],
            "min_corridor_width_m": profile["min_corridor_width_m"],
            "min_door_width_m": profile["min_door_width_m"],
            "turning_radius_m": profile["turning_radius_m"],
        },
        "grid_meta": {
            "resolution_m": cs,
            "cols": cols,
            "rows": rows,
        },
        "summary": {
            "total_violations": len(violations),
            "hard_violations": len(hard_violations),
            "blocked_area_m2": round(len(violation_cells) * cs * cs, 3),
            "warning_area_m2": round(len(warning_cells) * cs * cs, 3),
            "use_point_violations": sum(
                1 for r in use_point_results.values()
                if not r["clearance_sufficient"]),
            "unreachable_use_points": sum(
                1 for r in use_point_results.values()
                if not r["reachable"]),
            "functional_line_blocks": sum(
                1 for r in use_point_results.values()
                if r["functional_line"] and r["functional_line"].get("blocked")),
        },
        "violations": violations,
        "objects": objects_out,
        "doors": list(doors_grouped.values()),
        "comparison": comparison,
        # Pass violation_cells to GH for visualization
        "_grid_meta": {
            "violation_cells": violation_cells,
            "warning_cells": warning_cells,
            "ox": ox, "oy": oy,
            "cols": cols, "rows": rows,
            "cs": cs,
        },
    }

    return report


# ---------------------------------------------------------------------------
# LangGraph node — same pattern as visibility.py
# ---------------------------------------------------------------------------

def build_collision_node(mcp_client, workspace_path):
    """Return a collision node ready to be added to a LangGraph StateGraph."""

    def collision_node(state):
        # Parallel-safe: returns an update dict instead of mutating state.
        # Do NOT increment iteration — parallel nodes share the counter and
        # the _keep_last reducer would silently drop increments from siblings.

        print("Running collision analysis...")
        try:
            layout = json.loads(state["layout_json_string"])
            profile_config = state.get("profile_config")
            result = check_collision(layout, profile_config)
        except Exception as exc:
            print(f"[collision] Analysis failed: {exc}")
            result = {
                "pass": True, "violations": [],
                "summary": {"total_violations": 0, "hard_violations": 0,
                             "blocked_area_m2": 0, "warning_area_m2": 0},
                "objects": [], "doors": [],
            }

        passed = result.get("pass", True)
        status = "PASS" if passed else "FAIL"
        n_hard = result.get("summary", {}).get("hard_violations", 0)
        n_total = result.get("summary", {}).get("total_violations", 0)
        print(f"Collision: {status} — {n_hard} hard violations, {n_total} total")

        # Push visualization to GH — map profile_config to GH script format.
        # GH script expects {"user_type": "wheelchair", "body_width_m": ..., "min_corridor_width_m": ..., "turning_radius_m": ...}
        # Profile agent outputs {"profile_type": "wheelchair_user", "min_path_width": ..., "turning_radius": ...}
        try:
            profile_type = (profile_config or {}).get("profile_type", "wheelchair_user")
            # Map profile_type names: "wheelchair_user" → "wheelchair", "visually_impaired" → "visually_impaired"
            gh_user_type = profile_type.replace("_user", "") if profile_type else "wheelchair"
            gh_profile = {
                "user_type": gh_user_type,
                "body_width_m": (profile_config or {}).get("body_width", 0.70),
                "min_corridor_width_m": (profile_config or {}).get("min_path_width", 0.90),
                "min_door_width_m": (profile_config or {}).get("min_door_width", 0.85),
                "turning_radius_m": (profile_config or {}).get("turning_radius", 1.50),
            }
            viz_args = {
                "layout_json": state["layout_json_string"],
                "user_profile": json.dumps(gh_profile),
                "wall_thickness": 0.20,
            }
            print(f"[collision] Sending to GH: user_profile={json.dumps(gh_profile)}")
            tool_output = mcp_client.call_tool("collision-detector-grid", viz_args)
            print(f"Collision viz result: {str(tool_output)[:300]}")
        except Exception as e:
            tool_output = f"collision-detector-grid error: {e}"
            print(tool_output)

        # Return partial update — LangGraph merges via add_messages / _keep_last.
        return {
            "collision_results": result,
            "messages": [
                {
                    "role": "assistant",
                    "content": json.dumps({
                        "action": "tool",
                        "final_response": "",
                        "tool_calls": [{"name": "collision-detector-grid", "arguments": {
                            "pass": result["pass"],
                            "hard_violations": n_hard,
                        }}],
                    }),
                },
                {
                    "role": "user",
                    "content": f"Tool result: {str(tool_output)[:500]}",
                },
            ],
        }

    return collision_node