"""
GHPython Component: Grid-Based Collision Detector
Analyzes layout JSON for accessibility collisions using a clearance field.
Supports use_point / functional_point analysis for furniture interaction zones.

INPUTS:
    layout_json    (str)   Item  - Layout JSON string or file path
    user_profile   (str)   Item  - User profile JSON (user_type, body_width_m, etc.)
    wall_thickness (float) Item  - Wall thickness in meters (default: 0.20)
    cell_size      (float) Item  - Grid resolution in meters (default: 0.10)
    compare_json   (str)   Item  - Optional previous layout for before/after diff

OUTPUTS:
    a = pass_fail        (bool)
    b = violations       (list of str)
    c = violation_zones  (list of Curve)
    d = clearance_mesh   (Mesh)
    e = unified_json     (str) - Comprehensive unified report JSON
    f = new_violations   (list of str)
    g = new_zones        (list of Curve)
"""
import json
import math
import os
from collections import deque
import Rhino.Geometry as rg
import System.Drawing

# =============================================================================
# PROFILE DEFAULTS
# =============================================================================
PROFILE_DEFAULTS = {
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

# =============================================================================
# GEOMETRY HELPERS
# =============================================================================

def parse_layout(text):
    """Parse JSON string or file path into layout dict."""
    if text is None:
        return None
    text = str(text).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except:
        pass
    if os.path.isfile(text):
        try:
            with open(text, "r") as fh:
                return json.load(fh)
        except:
            pass
    return None


def get_profile(profile_json):
    """Parse user profile, merge with defaults."""
    profile = {}
    if profile_json:
        try:
            profile = json.loads(str(profile_json).strip())
        except:
            profile = {}
    user_type = profile.get("user_type", "wheelchair")
    defaults = PROFILE_DEFAULTS.get(user_type, PROFILE_DEFAULTS["wheelchair"])
    result = dict(defaults)
    for key in ("min_door_width_m", "min_corridor_width_m", "turning_radius_m", "body_width_m"):
        if key in profile:
            result[key] = float(profile[key])
    result["user_type"] = user_type
    return result


def _point_on_segment_t(seg_p1, seg_p2, pt, tolerance=0.02):
    """Return parameter t of pt projected onto segment [seg_p1, seg_p2], or None if not on it."""
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
    """Split a wall segment into parts that exclude door openings."""
    door_intervals = []
    for dp1, dp2 in door_segments:
        t1 = _point_on_segment_t(wp1, wp2, dp1)
        t2 = _point_on_segment_t(wp1, wp2, dp2)
        if t1 is not None and t2 is not None:
            t_min = min(t1, t2)
            t_max = max(t1, t2)
            door_intervals.append((t_min, t_max))

    if not door_intervals:
        return [(wp1, wp2)]

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


def buffer_wall_segment(p1, p2, half_thickness):
    """Convert a wall centerline segment into a rectangle polygon (4 corners)."""
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


# =============================================================================
# GRID RASTERIZATION
# =============================================================================

def rasterize_polygon(polygon_pts, grid, cols, rows, ox, oy, cs, value):
    """Scanline fill a closed polygon onto the grid."""
    n = len(polygon_pts)
    if n < 3:
        return
    gpts = []
    for pt in polygon_pts:
        gx = (pt[0] - ox) / cs
        gy = (pt[1] - oy) / cs
        gpts.append((gx, gy))

    min_gy = max(0, int(math.floor(min(p[1] for p in gpts))))
    max_gy = min(rows - 1, int(math.floor(max(p[1] for p in gpts))))

    for gy in range(min_gy, max_gy + 1):
        scanline_y = gy + 0.5
        intersections = []
        for i in range(n - 1):
            y0 = gpts[i][1]
            y1 = gpts[i + 1][1]
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


def rasterize_polygon_attributed(polygon_pts, grid, attrib_grid, cols, rows, ox, oy, cs, value, obj_index):
    """Scanline fill a closed polygon onto the grid, recording object attribution."""
    n = len(polygon_pts)
    if n < 3:
        return
    gpts = []
    for pt in polygon_pts:
        gx = (pt[0] - ox) / cs
        gy = (pt[1] - oy) / cs
        gpts.append((gx, gy))

    min_gy = max(0, int(math.floor(min(p[1] for p in gpts))))
    max_gy = min(rows - 1, int(math.floor(max(p[1] for p in gpts))))

    for gy in range(min_gy, max_gy + 1):
        scanline_y = gy + 0.5
        intersections = []
        for i in range(n - 1):
            y0 = gpts[i][1]
            y1 = gpts[i + 1][1]
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


# =============================================================================
# DISTANCE FIELD & ATTRIBUTION
# =============================================================================

def compute_distance_field(grid, cols, rows):
    """Brushfire BFS from all obstacle cells. Returns distance in cell units."""
    total = cols * rows
    dist = [0] * total
    queue = deque()

    for idx in range(total):
        if grid[idx] == -2:
            dist[idx] = 0
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
        if x > 0:
            nidx = idx - 1
            if dist[nidx] > d + 1:
                dist[nidx] = d + 1
                queue.append(nidx)
        if x < cols - 1:
            nidx = idx + 1
            if dist[nidx] > d + 1:
                dist[nidx] = d + 1
                queue.append(nidx)
        if y > 0:
            nidx = idx - cols
            if dist[nidx] > d + 1:
                dist[nidx] = d + 1
                queue.append(nidx)
        if y < rows - 1:
            nidx = idx + cols
            if dist[nidx] > d + 1:
                dist[nidx] = d + 1
                queue.append(nidx)

    return dist


def compute_nearest_obstacle(grid, attrib_grid, cols, rows):
    """BFS from obstacles, propagating which obstacle object is nearest to each cell."""
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
        if x > 0:
            nidx = idx - 1
            if dist[nidx] > d + 1:
                dist[nidx] = d + 1
                nearest[nidx] = obj_i
                queue.append(nidx)
        if x < cols - 1:
            nidx = idx + 1
            if dist[nidx] > d + 1:
                dist[nidx] = d + 1
                nearest[nidx] = obj_i
                queue.append(nidx)
        if y > 0:
            nidx = idx - cols
            if dist[nidx] > d + 1:
                dist[nidx] = d + 1
                nearest[nidx] = obj_i
                queue.append(nidx)
        if y < rows - 1:
            nidx = idx + cols
            if dist[nidx] > d + 1:
                dist[nidx] = d + 1
                nearest[nidx] = obj_i
                queue.append(nidx)

    return nearest


# =============================================================================
# USE-POINT & FUNCTIONAL-LINE ANALYSIS
# =============================================================================

def check_use_point_clearance(use_point, dist, attrib_grid, self_obj_index, cols, rows, ox, oy, cs, body_half_cells):
    """Check if use_point has sufficient clearance (ignoring self as obstacle).
    Returns dict with clearance_m, sufficient, deficit_m.
    """
    gx = int(round((use_point[0] - ox) / cs))
    gy = int(round((use_point[1] - oy) / cs))
    if gx < 0 or gx >= cols or gy < 0 or gy >= rows:
        required_m = body_half_cells * cs
        return {"clearance_m": 0.0, "sufficient": False, "deficit_m": round(required_m, 3)}

    idx = gy * cols + gx
    d = dist[idx]

    # If the use_point lands on its own object (obstacle cell attributed to self),
    # search the nearest non-self cell for actual clearance
    if d <= 0 and attrib_grid[idx] == self_obj_index:
        best_d = 999999
        search_r = body_half_cells + 3
        for dy_s in range(-search_r, search_r + 1):
            for dx_s in range(-search_r, search_r + 1):
                nx, ny = gx + dx_s, gy + dy_s
                if 0 <= nx < cols and 0 <= ny < rows:
                    ni = ny * cols + nx
                    if dist[ni] > 0 and dist[ni] < best_d:
                        # This cell is free space; its dist value is clearance from OTHER obstacles
                        best_d = dist[ni]
        d = best_d if best_d < 999999 else 0

    if d < 0:  # exterior
        required_m = body_half_cells * cs
        return {"clearance_m": 0.0, "sufficient": False, "deficit_m": round(required_m, 3)}

    clearance_m = d * cs
    required_m = body_half_cells * cs
    return {
        "clearance_m": round(clearance_m, 3),
        "sufficient": d >= body_half_cells,
        "deficit_m": round(max(0, required_m - clearance_m), 3),
    }


def compute_reachable_from_doors(doors, dist, cols, rows, ox, oy, cs, body_half_cells):
    """BFS from first door through all cells with clearance >= body_half_cells.
    Returns set of reachable cell indices.
    """
    if not doors:
        return set()

    # Find seed cells near first door
    first_door = None
    for door in doors:
        geom = door.get("geometry", [])
        if len(geom) == 2:
            first_door = door
            break
    if first_door is None:
        return set()

    geom = first_door["geometry"]
    mid_x = (geom[0][0] + geom[1][0]) / 2.0
    mid_y = (geom[0][1] + geom[1][1]) / 2.0
    dcx = int((mid_x - ox) / cs)
    dcy = int((mid_y - oy) / cs)

    search_radius = body_half_cells + 4
    seeds = set()
    for dy in range(-search_radius, search_radius + 1):
        for dx in range(-search_radius, search_radius + 1):
            nx, ny = dcx + dx, dcy + dy
            if 0 <= nx < cols and 0 <= ny < rows:
                ni = ny * cols + nx
                if dist[ni] >= body_half_cells:
                    seeds.add(ni)

    if not seeds:
        return set()

    reachable = set(seeds)
    bfs_q = deque(list(seeds))
    while bfs_q:
        ci = bfs_q.popleft()
        cx_pos = ci % cols
        cy_pos = ci // cols
        neighbors = []
        if cx_pos > 0:
            neighbors.append(ci - 1)
        if cx_pos < cols - 1:
            neighbors.append(ci + 1)
        if cy_pos > 0:
            neighbors.append(ci - cols)
        if cy_pos < rows - 1:
            neighbors.append(ci + cols)
        for ni in neighbors:
            if ni not in reachable and dist[ni] >= body_half_cells:
                reachable.add(ni)
                bfs_q.append(ni)

    return reachable


def check_use_point_reachability(use_point, reachable_set, dist, cols, rows, ox, oy, cs, body_half_cells):
    """Check if use_point is reachable from doors through passable cells."""
    if not reachable_set:
        return {"reachable": False, "reason": "no reachable cells computed (no doors?)"}

    gx = int(round((use_point[0] - ox) / cs))
    gy = int(round((use_point[1] - oy) / cs))
    if gx < 0 or gx >= cols or gy < 0 or gy >= rows:
        return {"reachable": False, "reason": "use_point outside grid bounds"}

    # Search neighborhood (use_point might be on furniture edge)
    search_r = max(3, body_half_cells + 1)
    for dy in range(-search_r, search_r + 1):
        for dx in range(-search_r, search_r + 1):
            nx, ny = gx + dx, gy + dy
            if 0 <= nx < cols and 0 <= ny < rows:
                ni = ny * cols + nx
                if ni in reachable_set:
                    return {"reachable": True, "reason": None}

    return {"reachable": False, "reason": "no passable path from doors to use_point"}


def bresenham(x0, y0, x1, y1):
    """Integer Bresenham line rasterization. Returns list of (x, y) grid cells."""
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


def check_functional_line(use_point, functional_point, grid, attrib_grid, obj_registry, self_obj_index, cols, rows, ox, oy, cs):
    """Check if line from use_point to functional_point is blocked by any obstacle (ignoring self)."""
    x0 = int(round((use_point[0] - ox) / cs))
    y0 = int(round((use_point[1] - oy) / cs))
    x1 = int(round((functional_point[0] - ox) / cs))
    y1 = int(round((functional_point[1] - oy) / cs))

    # Clamp to grid
    x0 = max(0, min(cols - 1, x0))
    y0 = max(0, min(rows - 1, y0))
    x1 = max(0, min(cols - 1, x1))
    y1 = max(0, min(rows - 1, y1))

    cells = bresenham(x0, y0, x1, y1)

    for (cx, cy) in cells:
        if cx < 0 or cx >= cols or cy < 0 or cy >= rows:
            continue
        idx = cy * cols + cx
        if grid[idx] == -2:
            obj_i = attrib_grid[idx]
            # Skip self
            if obj_i == self_obj_index:
                continue
            blocking_obj = obj_registry[obj_i] if 0 <= obj_i < len(obj_registry) else {"id": "unknown", "name": "unknown", "type": "unknown"}
            block_world = [round(ox + cx * cs, 3), round(oy + cy * cs, 3)]
            return {
                "blocked": True,
                "blocking_object_id": blocking_obj["id"],
                "blocking_object_name": blocking_obj["name"],
                "blocking_object_type": blocking_obj["type"],
                "block_point": block_world,
            }

    return {"blocked": False}


def compute_move_suggestion(use_point, dist, nearest, obj_registry, cols, rows, ox, oy, cs, body_half_cells):
    """Compute movement vector suggestion to resolve use_point clearance violation.
    Uses gradient of distance field to find direction away from nearest obstacle.
    """
    gx = int(round((use_point[0] - ox) / cs))
    gy = int(round((use_point[1] - oy) / cs))

    if gx < 1 or gx >= cols - 1 or gy < 1 or gy >= rows - 1:
        return None

    idx = gy * cols + gx
    current_d = dist[idx]
    if current_d < 0 or current_d >= body_half_cells:
        return None  # no suggestion needed

    # Gradient via central differences
    d_right = dist[idx + 1] if dist[idx + 1] >= 0 else 0
    d_left = dist[idx - 1] if dist[idx - 1] >= 0 else 0
    d_up = dist[idx + cols] if dist[idx + cols] >= 0 else 0
    d_down = dist[idx - cols] if dist[idx - cols] >= 0 else 0

    grad_x = (d_right - d_left) / 2.0
    grad_y = (d_up - d_down) / 2.0

    mag = math.sqrt(grad_x * grad_x + grad_y * grad_y)
    if mag < 0.01:
        return None  # flat field, no clear direction

    dx_norm = grad_x / mag
    dy_norm = grad_y / mag

    deficit_cells = body_half_cells - current_d
    deficit_m = deficit_cells * cs
    # Move distance: deficit adjusted by gradient effectiveness
    move_distance_m = deficit_m / min(mag, 1.0)

    nearest_obj_id = None
    if nearest[idx] >= 0 and nearest[idx] < len(obj_registry):
        nearest_obj_id = obj_registry[nearest[idx]]["id"]

    return {
        "direction": [round(dx_norm, 3), round(dy_norm, 3)],
        "distance_m": round(move_distance_m, 3),
        "deficit_m": round(deficit_m, 3),
        "nearest_obstacle_id": nearest_obj_id,
    }


# =============================================================================
# ANALYSIS
# =============================================================================

def analyze_layout(layout, profile, wall_thick, cs):
    """Run full grid analysis with use_point/functional_point support.
    Returns dict with all analysis results.
    """
    outline = layout.get("outline", [])
    if not outline or len(outline) < 3:
        return {
            "violations": ["No valid outline found"],
            "violation_cells": [],
            "warning_cells": [],
            "dist": None,
            "cols": 0, "rows": 0, "ox": 0, "oy": 0,
            "object_violations": [],
            "use_point_results": {},
            "door_violations": [],
            "turning_violations": [],
        }

    # Bounding box
    all_x = [p[0] for p in outline]
    all_y = [p[1] for p in outline]
    ox = min(all_x)
    oy = min(all_y)
    max_x = max(all_x)
    max_y = max(all_y)
    cols = int(math.ceil((max_x - ox) / cs)) + 1
    rows = int(math.ceil((max_y - oy) / cs)) + 1

    # Initialize grids
    total = cols * rows
    grid = [-1] * total
    attrib_grid = [-1] * total

    # Object registry
    obj_registry = []

    # Rasterize outline interior
    rasterize_polygon(outline, grid, cols, rows, ox, oy, cs, 0)

    # Rasterize obstacles with attribution
    half_t = wall_thick / 2.0

    # Collect door segments
    door_segments = []
    for door in layout.get("doors", []):
        dg = door.get("geometry", [])
        if len(dg) == 2:
            door_segments.append((dg[0], dg[1]))

    # Walls (structure)
    for wall in layout.get("structure", []):
        geom = wall.get("geometry", [])
        if len(geom) != 2:
            continue
        obj_index = len(obj_registry)
        obj_registry.append({
            "id": wall.get("id", "unknown"),
            "name": wall.get("name", "unnamed wall"),
            "type": "structure",
            "use_point": None,
            "functional_point": None,
        })
        wp1, wp2 = geom[0], geom[1]
        wall_parts = _split_wall_at_doors(wp1, wp2, door_segments, half_t)
        for seg_p1, seg_p2 in wall_parts:
            rect = buffer_wall_segment(seg_p1, seg_p2, half_t)
            if rect:
                rasterize_polygon_attributed(rect, grid, attrib_grid, cols, rows, ox, oy, cs, -2, obj_index)

    # Furniture
    for furn in layout.get("furniture", []):
        geom = furn.get("geometry", [])
        if len(geom) >= 3:
            obj_index = len(obj_registry)
            obj_registry.append({
                "id": furn.get("id", "unknown"),
                "name": furn.get("name", "unnamed furniture"),
                "type": "furniture",
                "use_point": furn.get("use_point", None),
                "functional_point": furn.get("functional_point", None),
            })
            rasterize_polygon_attributed(geom, grid, attrib_grid, cols, rows, ox, oy, cs, -2, obj_index)

    # MEP
    for mep_item in layout.get("mep", []):
        geom = mep_item.get("geometry", [])
        if len(geom) >= 3:
            obj_index = len(obj_registry)
            obj_registry.append({
                "id": mep_item.get("id", "unknown"),
                "name": mep_item.get("name", "unnamed mep"),
                "type": "mep",
                "use_point": mep_item.get("use_point", None),
                "functional_point": mep_item.get("functional_point", None),
            })
            rasterize_polygon_attributed(geom, grid, attrib_grid, cols, rows, ox, oy, cs, -2, obj_index)

    # Compute distance field and nearest-obstacle attribution
    dist = compute_distance_field(grid, cols, rows)
    nearest = compute_nearest_obstacle(grid, attrib_grid, cols, rows)

    # Thresholds
    body_half_cells = int(math.ceil((profile["body_width_m"] / 2.0) / cs))
    corridor_half_cells = int(math.ceil((profile["min_corridor_width_m"] / 2.0) / cs))

    # Find violation cells with per-object attribution
    violation_cells = []
    warning_cells = []
    obj_violation_data = {}  # obj_index -> {blocked_cells, warning_cells, min_clearance_m}

    for idx in range(total):
        if dist[idx] <= 0 or dist[idx] == -1:
            continue
        if dist[idx] < body_half_cells:
            violation_cells.append(idx)
            obj_i = nearest[idx]
            if obj_i >= 0:
                if obj_i not in obj_violation_data:
                    obj_violation_data[obj_i] = {"blocked_cells": 0, "warning_cells": 0, "min_clearance_m": 999.0}
                obj_violation_data[obj_i]["blocked_cells"] += 1
                clearance_m = dist[idx] * cs
                if clearance_m < obj_violation_data[obj_i]["min_clearance_m"]:
                    obj_violation_data[obj_i]["min_clearance_m"] = clearance_m
        elif dist[idx] < corridor_half_cells:
            warning_cells.append(idx)
            obj_i = nearest[idx]
            if obj_i >= 0:
                if obj_i not in obj_violation_data:
                    obj_violation_data[obj_i] = {"blocked_cells": 0, "warning_cells": 0, "min_clearance_m": 999.0}
                obj_violation_data[obj_i]["warning_cells"] += 1
                clearance_m = dist[idx] * cs
                if clearance_m < obj_violation_data[obj_i]["min_clearance_m"]:
                    obj_violation_data[obj_i]["min_clearance_m"] = clearance_m

    # Build violations list
    violations = []

    if violation_cells:
        violations.append(
            "BLOCKED: {} cells ({:.2f} m^2) impassable - clearance < {:.2f}m (body width {:.2f}m)".format(
                len(violation_cells),
                len(violation_cells) * cs * cs,
                profile["body_width_m"] / 2.0,
                profile["body_width_m"],
            )
        )
    if warning_cells:
        violations.append(
            "WARNING: {} cells ({:.2f} m^2) below corridor spec - clearance < {:.2f}m (min corridor {:.2f}m)".format(
                len(warning_cells),
                len(warning_cells) * cs * cs,
                profile["min_corridor_width_m"] / 2.0,
                profile["min_corridor_width_m"],
            )
        )

    # Door width check
    DOOR_TOLERANCE = 0.01
    door_violations = []
    for door in layout.get("doors", []):
        geom = door.get("geometry", [])
        if len(geom) == 2:
            dx = geom[1][0] - geom[0][0]
            dy = geom[1][1] - geom[0][1]
            width = math.sqrt(dx * dx + dy * dy)
            if width < profile["min_door_width_m"] - DOOR_TOLERANCE:
                violations.append(
                    "DOOR_WIDTH: '{}' ({}) width {:.2f}m < required {:.2f}m (deficit {:.2f}m)".format(
                        door.get("name", door.get("id", "?")),
                        door.get("id", "?"),
                        width,
                        profile["min_door_width_m"],
                        profile["min_door_width_m"] - width,
                    )
                )
                door_violations.append({
                    "id": door.get("id", "unknown"),
                    "name": door.get("name", "unnamed door"),
                    "violation_type": "width",
                    "actual_m": round(width, 3),
                    "required_m": profile["min_door_width_m"],
                    "deficit_m": round(profile["min_door_width_m"] - width, 3),
                })

    # Turning radius check
    turning_cells = int(math.ceil(profile["turning_radius_m"] / cs))
    turning_violations = []
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
        max_clearance_found = 0
        for dy_s in range(-search_r, search_r + 1, 2):
            for dx_s in range(-search_r, search_r + 1, 2):
                gx = cx + dx_s
                gy = cy + dy_s
                if 0 <= gx < cols and 0 <= gy < rows:
                    nidx = gy * cols + gx
                    cell_dist = dist[nidx]
                    if cell_dist >= turning_cells:
                        found = True
                        break
                    if cell_dist > max_clearance_found:
                        max_clearance_found = cell_dist
            if found:
                break
        if not found:
            available_radius = max_clearance_found * cs
            violations.append(
                "TURNING: '{}' ({}) need {:.2f}m radius, available {:.2f}m (deficit {:.2f}m)".format(
                    door.get("name", door.get("id", "?")),
                    door.get("id", "?"),
                    profile["turning_radius_m"],
                    available_radius,
                    profile["turning_radius_m"] - available_radius,
                )
            )
            turning_violations.append({
                "id": door.get("id", "unknown"),
                "name": door.get("name", "unnamed door"),
                "violation_type": "turning_radius",
                "required_m": profile["turning_radius_m"],
                "available_m": round(available_radius, 3),
                "deficit_m": round(profile["turning_radius_m"] - available_radius, 3),
            })

    # Compute reachable set from doors (for connectivity + use_point reachability)
    reachable_set = compute_reachable_from_doors(layout.get("doors", []), dist, cols, rows, ox, oy, cs, body_half_cells)

    # Connectivity check
    doors = layout.get("doors", [])
    if len(doors) > 1 and reachable_set:
        search_radius = body_half_cells + 4
        for door in doors[1:]:
            geom = door.get("geometry", [])
            if len(geom) != 2:
                continue
            mid_x = (geom[0][0] + geom[1][0]) / 2.0
            mid_y = (geom[0][1] + geom[1][1]) / 2.0
            dcx = int((mid_x - ox) / cs)
            dcy = int((mid_y - oy) / cs)
            seeds = set()
            for ddy in range(-search_radius, search_radius + 1):
                for ddx in range(-search_radius, search_radius + 1):
                    nx, ny = dcx + ddx, dcy + ddy
                    if 0 <= nx < cols and 0 <= ny < rows:
                        ni = ny * cols + nx
                        if dist[ni] >= body_half_cells:
                            seeds.add(ni)
            if not seeds or not seeds.intersection(reachable_set):
                violations.append(
                    "CONNECTIVITY: Door '{}' ({}) unreachable for {} profile".format(
                        door.get("name", door.get("id", "?")),
                        door.get("id", "?"),
                        profile["user_type"],
                    )
                )

    # =========================================================================
    # USE-POINT & FUNCTIONAL-LINE ANALYSIS
    # =========================================================================
    use_point_results = {}  # obj_index -> analysis dict

    for obj_i, obj_info in enumerate(obj_registry):
        up = obj_info.get("use_point")
        if up is None:
            continue

        # Clearance check
        clearance = check_use_point_clearance(up, dist, attrib_grid, obj_i, cols, rows, ox, oy, cs, body_half_cells)

        # Reachability check
        reachability = check_use_point_reachability(up, reachable_set, dist, cols, rows, ox, oy, cs, body_half_cells)

        # Movement suggestion (only if insufficient clearance)
        move_sug = None
        if not clearance["sufficient"]:
            move_sug = compute_move_suggestion(up, dist, nearest, obj_registry, cols, rows, ox, oy, cs, body_half_cells)

        # Functional line check
        fp = obj_info.get("functional_point")
        func_line = None
        if fp is not None:
            func_line = check_functional_line(up, fp, grid, attrib_grid, obj_registry, obj_i, cols, rows, ox, oy, cs)

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

        # Add human-readable violations
        if not clearance["sufficient"]:
            violations.append(
                "USE_POINT: '{}' ({}) clearance {:.2f}m < required {:.2f}m (deficit {:.2f}m)".format(
                    obj_info["name"], obj_info["id"],
                    clearance["clearance_m"], body_half_cells * cs, clearance["deficit_m"],
                )
            )
        if not reachability["reachable"]:
            violations.append(
                "USE_POINT_UNREACHABLE: '{}' ({}) - {}".format(
                    obj_info["name"], obj_info["id"],
                    reachability.get("reason", "blocked"),
                )
            )
        if func_line and func_line.get("blocked"):
            violations.append(
                "FUNCTIONAL_LINE: '{}' ({}) line to functional_point blocked by '{}' ({})".format(
                    obj_info["name"], obj_info["id"],
                    func_line["blocking_object_name"], func_line["blocking_object_id"],
                )
            )

    return {
        "violations": violations,
        "violation_cells": violation_cells,
        "warning_cells": warning_cells,
        "dist": dist,
        "cols": cols, "rows": rows, "ox": ox, "oy": oy,
        "obj_registry": obj_registry,
        "obj_violation_data": obj_violation_data,
        "use_point_results": use_point_results,
        "door_violations": door_violations,
        "turning_violations": turning_violations,
        "grid": grid,
        "attrib_grid": attrib_grid,
        "nearest": nearest,
    }


# =============================================================================
# VISUALIZATION HELPERS
# =============================================================================

def cells_to_zones(cell_list, cols, rows, ox, oy, cs):
    """Group adjacent cells into bounding box rectangles."""
    if not cell_list:
        return []

    cell_set = set(cell_list)
    visited = set()
    rectangles = []

    for cell in cell_list:
        if cell in visited:
            continue
        cluster = []
        stack = [cell]
        while stack:
            c = stack.pop()
            if c in visited or c not in cell_set:
                continue
            visited.add(c)
            cluster.append(c)
            x = c % cols
            y = c // cols
            if x > 0 and (c - 1) not in visited:
                stack.append(c - 1)
            if x < cols - 1 and (c + 1) not in visited:
                stack.append(c + 1)
            if y > 0 and (c - cols) not in visited:
                stack.append(c - cols)
            if y < rows - 1 and (c + cols) not in visited:
                stack.append(c + cols)

        if len(cluster) < 4:
            continue

        xs = [c % cols for c in cluster]
        ys = [c // cols for c in cluster]
        min_wx = min(xs) * cs + ox
        max_wx = (max(xs) + 1) * cs + ox
        min_wy = min(ys) * cs + oy
        max_wy = (max(ys) + 1) * cs + oy

        p0 = rg.Point3d(min_wx, min_wy, 0)
        p1 = rg.Point3d(max_wx, min_wy, 0)
        p2 = rg.Point3d(max_wx, max_wy, 0)
        p3 = rg.Point3d(min_wx, max_wy, 0)
        pts = [p0, p1, p2, p3, p0]
        polyline = rg.Polyline(pts)
        rectangles.append(polyline.ToPolylineCurve())

    return rectangles


def create_clearance_mesh(dist, cols, rows, ox, oy, cs, threshold_cells):
    """Create a colored mesh showing clearance field."""
    mesh = rg.Mesh()
    limit = threshold_cells * 3
    for idx in range(cols * rows):
        d = dist[idx]
        if d < 0 or d > limit:
            continue
        x = idx % cols
        y = idx // cols
        wx = ox + x * cs
        wy = oy + y * cs
        vi = mesh.Vertices.Count
        mesh.Vertices.Add(wx, wy, 0)
        mesh.Vertices.Add(wx + cs, wy, 0)
        mesh.Vertices.Add(wx + cs, wy + cs, 0)
        mesh.Vertices.Add(wx, wy + cs, 0)
        mesh.Faces.AddFace(vi, vi + 1, vi + 2, vi + 3)
        if d < threshold_cells:
            r, g, b = 220, 40, 40
        elif d < threshold_cells * 1.5:
            t = (d - threshold_cells) / (threshold_cells * 0.5)
            r = int(220 - t * 100)
            g = int(40 + t * 125)
            b = 40
        else:
            r, g, b = 60, 180, 60
        color = System.Drawing.Color.FromArgb(180, r, g, b)
        mesh.VertexColors.Add(color)
        mesh.VertexColors.Add(color)
        mesh.VertexColors.Add(color)
        mesh.VertexColors.Add(color)
    return mesh


# =============================================================================
# UNIFIED REPORT BUILDER
# =============================================================================

def build_unified_report(result, profile, cs):
    """Build the comprehensive unified JSON report from analysis results."""
    obj_registry = result["obj_registry"]
    obj_violation_data = result["obj_violation_data"]
    use_point_results = result["use_point_results"]
    door_violations = result["door_violations"]
    turning_violations = result["turning_violations"]
    violations = result["violations"]
    violation_cells = result["violation_cells"]
    warning_cells = result["warning_cells"]

    body_half_cells = int(math.ceil((profile["body_width_m"] / 2.0) / cs))

    # Count use_point violations
    up_violations_count = 0
    func_line_blocks = 0
    unreachable_count = 0
    for obj_i, upr in use_point_results.items():
        if not upr["clearance_sufficient"]:
            up_violations_count += 1
        if not upr["reachable"]:
            unreachable_count += 1
        if upr["functional_line"] and upr["functional_line"].get("blocked"):
            func_line_blocks += 1

    # Summary
    hard_violations = [v for v in violations if not v.startswith("WARNING:")]
    pass_fail = len(hard_violations) == 0

    summary = {
        "total_violations": len(violations),
        "blocked_area_m2": round(len(violation_cells) * cs * cs, 3),
        "warning_area_m2": round(len(warning_cells) * cs * cs, 3),
        "use_point_violations": up_violations_count,
        "functional_line_blocks": func_line_blocks,
        "unreachable_use_points": unreachable_count,
    }

    # Build per-object entries
    objects_list = []
    for obj_i, obj_info in enumerate(obj_registry):
        has_clearance_violation = obj_i in obj_violation_data
        has_use_point = obj_i in use_point_results

        if not has_clearance_violation and not has_use_point:
            continue

        entry = {
            "id": obj_info["id"],
            "name": obj_info["name"],
            "object_type": obj_info["type"],
            "clearance_violation": None,
            "use_point_analysis": None,
            "functional_line_analysis": None,
        }

        # Clearance violation data
        if has_clearance_violation:
            data = obj_violation_data[obj_i]
            entry["clearance_violation"] = {
                "blocked_cells": data["blocked_cells"],
                "blocked_area_m2": round(data["blocked_cells"] * cs * cs, 3),
                "warning_cells": data["warning_cells"],
                "warning_area_m2": round(data["warning_cells"] * cs * cs, 3),
                "min_clearance_m": round(data["min_clearance_m"], 3),
                "required_clearance_m": round(body_half_cells * cs, 3),
                "deficit_m": round(max(0, body_half_cells * cs - data["min_clearance_m"]), 3),
            }

        # Use-point analysis
        if has_use_point:
            upr = use_point_results[obj_i]
            entry["use_point_analysis"] = {
                "use_point": upr["use_point"],
                "clearance_m": upr["clearance_m"],
                "sufficient": upr["clearance_sufficient"],
                "deficit_m": upr["deficit_m"],
                "reachable": upr["reachable"],
                "reachability_reason": upr["reachability_reason"],
                "move_suggestion": upr["move_suggestion"],
            }
            # Functional line
            if upr["functional_line"] is not None:
                entry["functional_line_analysis"] = {
                    "functional_point": upr["functional_point"],
                    "blocked": upr["functional_line"]["blocked"],
                }
                if upr["functional_line"]["blocked"]:
                    entry["functional_line_analysis"]["blocking_object_id"] = upr["functional_line"]["blocking_object_id"]
                    entry["functional_line_analysis"]["blocking_object_name"] = upr["functional_line"]["blocking_object_name"]
                    entry["functional_line_analysis"]["blocking_object_type"] = upr["functional_line"]["blocking_object_type"]
                    entry["functional_line_analysis"]["block_point"] = upr["functional_line"]["block_point"]

        objects_list.append(entry)

    # Sort objects by severity (blocked_cells descending)
    def sort_key(obj):
        cv = obj.get("clearance_violation")
        if cv:
            return (0, -cv["blocked_cells"])
        return (1, 0)
    objects_list.sort(key=sort_key)

    # Door violations grouped by door
    doors_grouped = {}
    for dv in door_violations:
        did = dv["id"]
        if did not in doors_grouped:
            doors_grouped[did] = {"id": did, "name": dv["name"], "violations": []}
        doors_grouped[did]["violations"].append({
            "type": dv["violation_type"],
            "actual_m": dv["actual_m"],
            "required_m": dv["required_m"],
            "deficit_m": dv["deficit_m"],
        })
    for tv in turning_violations:
        did = tv["id"]
        if did not in doors_grouped:
            doors_grouped[did] = {"id": did, "name": tv["name"], "violations": []}
        doors_grouped[did]["violations"].append({
            "type": tv["violation_type"],
            "required_m": tv["required_m"],
            "available_m": tv["available_m"],
            "deficit_m": tv["deficit_m"],
        })

    # Build final report
    report = {
        "pass": pass_fail,
        "profile": {
            "user_type": profile["user_type"],
            "body_width_m": profile["body_width_m"],
            "min_corridor_width_m": profile["min_corridor_width_m"],
            "min_door_width_m": profile["min_door_width_m"],
            "turning_radius_m": profile["turning_radius_m"],
        },
        "grid": {
            "resolution_m": cs,
            "cols": result["cols"],
            "rows": result["rows"],
        },
        "summary": summary,
        "objects": objects_list,
        "doors": list(doors_grouped.values()),
    }

    return report, pass_fail


# =============================================================================
# MAIN EXECUTION
# =============================================================================

# Initialize outputs
a = True
b = []
c = []
d = None
e = ""
f = []
g = []

# Read inputs with defaults
try:
    _layout_json = layout_json
except NameError:
    _layout_json = None

try:
    _user_profile = user_profile
except NameError:
    _user_profile = None

try:
    _wall_thickness = float(wall_thickness) if wall_thickness is not None else 0.20
except (NameError, TypeError, ValueError):
    _wall_thickness = 0.20

try:
    _cell_size = float(cell_size) if cell_size is not None else 0.10
except (NameError, TypeError, ValueError):
    _cell_size = 0.10

try:
    _compare_json = compare_json
except NameError:
    _compare_json = None

# Parse layout
layout = parse_layout(_layout_json)
if layout is None:
    a = False
    b = ["ERROR: Could not parse layout_json input"]
    e = json.dumps({"pass": False, "error": "Could not parse layout_json"})
else:
    profile = get_profile(_user_profile)

    # Run analysis
    result = analyze_layout(layout, profile, _wall_thickness, _cell_size)

    violations = result["violations"]
    violation_cells = result["violation_cells"]
    warning_cells = result["warning_cells"]
    dist = result["dist"]
    cols = result["cols"]
    rows = result["rows"]
    ox = result["ox"]
    oy = result["oy"]

    # Build unified report
    report, pass_fail = build_unified_report(result, profile, _cell_size)
    a = pass_fail
    b = violations

    # Generate visual geometry
    all_flagged = violation_cells + warning_cells
    if all_flagged:
        c = cells_to_zones(all_flagged, cols, rows, ox, oy, _cell_size)

    # Generate clearance mesh
    if dist is not None:
        corridor_half_cells = int(math.ceil((profile["min_corridor_width_m"] / 2.0) / _cell_size))
        d = create_clearance_mesh(dist, cols, rows, ox, oy, _cell_size, corridor_half_cells)

    # Before/after comparison
    compare_layout = parse_layout(_compare_json)
    if compare_layout is not None:
        prev_result = analyze_layout(compare_layout, profile, _wall_thickness, _cell_size)
        prev_violations = prev_result["violations"]
        prev_cells = prev_result["violation_cells"]
        prev_set = set(prev_violations)
        f = [v for v in violations if v not in prev_set]
        prev_cell_set = set(prev_cells)
        new_cells = [c_idx for c_idx in violation_cells if c_idx not in prev_cell_set]
        if new_cells and dist is not None:
            g = cells_to_zones(new_cells, cols, rows, ox, oy, _cell_size)
        # Add comparison to report
        report["comparison"] = {
            "has_previous": True,
            "new_violation_count": len(f),
            "new_violations": f,
        }
    else:
        f = violations
        g = c

    # Unified JSON output
    e = json.dumps(report, indent=2)
