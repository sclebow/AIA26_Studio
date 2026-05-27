"""
nodes/path_analysis.py — Pathfinding at room level (BFS) and object level (A*).

Mode 1 (no furniture): BFS through the door graph between all room pairs.
  - Uses polylabel to find a guaranteed interior point for any room shape.
  - Edge weight = euclidean distance between the two rooms' interior points.
  - Also reports longest path (worst-case egress distance across the layout).

Mode 2 (furniture present): A* on a per-room 2D grid between object centroids.
  - Grid resolution: 0.1m per cell.
  - Furniture polygons are marked as obstacles on the grid.
  - Only objects sharing the same roomId are paired.
  - Also reports longest path among all object pairs.

Requires: polylabel, shapely
"""

from __future__ import annotations
import heapq
import json
import math
from collections import deque
from typing import Any

from shapely.geometry import Point, Polygon
from shapely.prepared import prep

GRID_RESOLUTION = 0.5  # metres per cell for Mode 2 A* grid


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _has_furniture(layout: dict) -> bool:
    return bool(layout.get("objects") or layout.get("furniture"))


def _make_polygon(pts: list) -> Polygon:
    return Polygon(pts)


def _interior_point(pts: list) -> tuple[float, float]:
    """
    Returns a point guaranteed to be inside the polygon.
    Prefers centroid (geometric centre) when it falls inside.
    Falls back to shapely's representative_point() for concave/irregular shapes
    where the centroid can land outside (L-shapes, T-shapes, thin corridors).
    """
    poly = Polygon(pts)
    centroid = poly.centroid
    if poly.contains(centroid):
        return (centroid.x, centroid.y)
    rp = poly.representative_point()
    return (rp.x, rp.y)


def _euclidean(a: tuple, b: tuple) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


# ---------------------------------------------------------------------------
# Mode 1 — Room-level BFS
# ---------------------------------------------------------------------------

def _build_room_graph(layout: dict) -> tuple[dict, dict, dict]:
    """
    Build an adjacency graph from rooms and doors.
    Nodes = room ids. Edges = doors connecting two rooms.
    Edge weight = euclidean distance between the two rooms' interior points.
    Returns (graph, interior_pts, id_to_name).
    """
    rooms = layout.get("rooms", [])
    doors = layout.get("doors", [])

    # Map id → readable name for output; keyed by id to match connectsRooms values
    id_to_name: dict[str, str] = {
        r.get("id"): r.get("name") or r.get("id")
        for r in rooms
    }

    # Compute interior point for each room; keyed by id (matches connectsRooms)
    interior_pts: dict[str, tuple] = {}
    for room in rooms:
        geom = room.get("geometry")
        if not geom:
            continue
        rid = room.get("id") or room.get("name")
        interior_pts[rid] = _interior_point(geom)

    # Build adjacency list: rid → [(neighbor_rid, door_id, distance)]
    graph: dict[str, list] = {rid: [] for rid in interior_pts}
    for door in doors:
        connects = door.get("attributes", {}).get(
            "connectsRooms", door.get("connects", []))
        if len(connects) != 2:
            continue
        r1, r2 = connects
        if r1 not in graph or r2 not in graph:
            continue
        dist = _euclidean(interior_pts[r1], interior_pts[r2])
        did = door.get("id", "door")
        graph[r1].append((r2, did, dist))
        graph[r2].append((r1, did, dist))

    return graph, interior_pts, id_to_name


def _bfs_path(
    graph: dict,
    interior_pts: dict,
    id_to_name: dict,
    start: str,
    end: str,
) -> tuple[list[str], float] | tuple[None, None]:
    """
    BFS finds the path with fewest door traversals (hops).
    Distance is then computed by summing euclidean gaps between consecutive
    room interior points along that path — not a weighted shortest path,
    but representative of actual travel length for the BFS-chosen route.
    Path is returned as human-readable room names via id_to_name.
    """
    if start == end:
        return [id_to_name.get(start, start)], 0.0
    if start not in graph or end not in graph:
        return None, None

    visited = {start}
    came_from: dict[str, str] = {}
    queue = deque([start])

    while queue:
        current = queue.popleft()
        for neighbor, _door_id, _dist in graph[current]:
            if neighbor in visited:
                continue
            visited.add(neighbor)
            came_from[neighbor] = current
            if neighbor == end:
                # Reconstruct id sequence from came_from map
                path_ids: list[str] = []
                node = end
                while node in came_from:
                    path_ids.append(node)
                    node = came_from[node]
                path_ids.append(start)
                path_ids.reverse()
                # Sum euclidean distances between consecutive interior points
                total = sum(
                    _euclidean(interior_pts[path_ids[i]], interior_pts[path_ids[i + 1]])
                    for i in range(len(path_ids) - 1)
                )
                return [id_to_name.get(nid, nid) for nid in path_ids], round(total, 3)
            queue.append(neighbor)

    return None, None


def _run_mode1(layout: dict) -> dict[str, Any]:
    """Run BFS for all room pairs and identify the worst-case egress path."""
    graph, interior_pts, id_to_name = _build_room_graph(layout)
    room_ids = list(graph.keys())

    pairs: list[dict] = []
    worst_case: dict = {"from": None, "to": None, "distance": 0.0}

    for i, src in enumerate(room_ids):
        for tgt in room_ids[i + 1:]:
            path, dist = _bfs_path(graph, interior_pts, id_to_name, src, tgt)
            src_name = id_to_name.get(src, src)
            tgt_name = id_to_name.get(tgt, tgt)
            if path is None:
                pairs.append({
                    "source": src_name, "target": tgt_name,
                    "path": [], "steps": 0, "distance": 0.0,
                    "status": "unreachable",
                })
            else:
                pairs.append({
                    "source": src_name, "target": tgt_name,
                    "path": path, "steps": len(path) - 1,
                    "distance": dist, "status": "reachable",
                })
                if dist > worst_case["distance"]:
                    worst_case = {"from": src_name, "to": tgt_name, "distance": dist}

    return {"pairs": pairs, "worst_case": worst_case}


# ---------------------------------------------------------------------------
# Mode 2 — Object-level A*
# ---------------------------------------------------------------------------

def _build_grid(
    room_polygon: Polygon,
) -> tuple[list[list[bool]], float, float, int, int]:
    """
    Rasterise room polygon into a 2D boolean grid at GRID_RESOLUTION.
    True = passable (inside room). False = wall (outside room boundary).
    No furniture is marked here — call _mark_obstacles() per pair.
    """
    minx, miny, maxx, maxy = room_polygon.bounds
    cols = int(math.ceil((maxx - minx) / GRID_RESOLUTION)) + 1
    rows = int(math.ceil((maxy - miny) / GRID_RESOLUTION)) + 1

    prepared_room = prep(room_polygon)
    grid: list[list[bool]] = [[False] * cols for _ in range(rows)]

    for row in range(rows):
        for col in range(cols):
            wx = minx + col * GRID_RESOLUTION
            wy = miny + row * GRID_RESOLUTION
            if prepared_room.contains(Point(wx, wy)):
                grid[row][col] = True

    return grid, minx, miny, cols, rows


def _mark_obstacles(
    grid: list[list[bool]],
    obstacle_poly: Polygon,
    origin_x: float, origin_y: float,
    cols: int, rows: int,
) -> None:
    """
    Mark cells inside obstacle_poly as impassable on the grid in-place.
    Scans only the obstacle's bounding box for efficiency.
    """
    prepared_obs = prep(obstacle_poly)
    obs_minx, obs_miny, obs_maxx, obs_maxy = obstacle_poly.bounds
    col_start = max(0, int((obs_minx - origin_x) / GRID_RESOLUTION) - 1)
    col_end   = min(cols, int((obs_maxx - origin_x) / GRID_RESOLUTION) + 2)
    row_start = max(0, int((obs_miny - origin_y) / GRID_RESOLUTION) - 1)
    row_end   = min(rows, int((obs_maxy - origin_y) / GRID_RESOLUTION) + 2)
    for row in range(row_start, row_end):
        for col in range(col_start, col_end):
            wx = origin_x + col * GRID_RESOLUTION
            wy = origin_y + row * GRID_RESOLUTION
            if prepared_obs.contains(Point(wx, wy)):
                grid[row][col] = False


def _nearest_free_cell(
    grid: list[list[bool]],
    rows: int, cols: int,
    start_row: int, start_col: int,
    max_radius: int = 10,
) -> tuple[int, int] | None:
    """
    Return the nearest free cell to (start_row, start_col) via square spiral search.
    Used when an object's centroid cell lands inside an obstacle polygon.
    Returns None if no free cell found within max_radius.
    """
    if grid[start_row][start_col]:
        return (start_row, start_col)
    for radius in range(1, max_radius + 1):
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if abs(dr) != radius and abs(dc) != radius:
                    continue  # only check the outer ring of the square
                r, c = start_row + dr, start_col + dc
                if 0 <= r < rows and 0 <= c < cols and grid[r][c]:
                    return (r, c)
    return None


def _world_to_cell(
    wx: float, wy: float,
    origin_x: float, origin_y: float,
    cols: int, rows: int,
) -> tuple[int, int]:
    """Convert world coordinates to grid (row, col), clamped to grid bounds."""
    col = max(0, min(cols - 1, int((wx - origin_x) / GRID_RESOLUTION)))
    row = max(0, min(rows - 1, int((wy - origin_y) / GRID_RESOLUTION)))
    return row, col


def _astar(
    grid: list[list[bool]],
    rows: int, cols: int,
    start: tuple[int, int],
    end: tuple[int, int],
) -> tuple[list[tuple], float] | tuple[None, None]:
    """
    A* on the 2D grid with 8-directional movement.
    Heuristic: euclidean distance to goal (admissible for 8-dir movement).
    Returns (cell path, total distance in grid units) or (None, None).
    Distance in grid units × GRID_RESOLUTION = metres.
    """
    def h(a: tuple, b: tuple) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    # Heap entries: (f_score, g_score, cell)
    open_heap: list = [(h(start, end), 0.0, start)]
    g_score: dict[tuple, float] = {start: 0.0}
    came_from: dict[tuple, tuple] = {}

    while open_heap:
        _f, g, current = heapq.heappop(open_heap)
        if g > g_score.get(current, float("inf")):
            continue  # stale heap entry — skip

        if current == end:
            # Reconstruct path from came_from map
            path: list[tuple] = []
            node = end
            while node in came_from:
                path.append(node)
                node = came_from[node]
            path.append(start)
            path.reverse()
            return path, g

        r, c = current
        # 8-directional neighbours: cardinal cost 1.0, diagonal cost √2
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols and grid[nr][nc]):
                continue
            step = math.sqrt(dr * dr + dc * dc)
            new_g = g + step
            neighbor = (nr, nc)
            if new_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = new_g
                came_from[neighbor] = current
                heapq.heappush(open_heap, (new_g + h(neighbor, end), new_g, neighbor))

    return None, None


def _run_mode2(layout: dict) -> dict[str, Any]:
    """
    A* pathfinding between object centroids within each room.
    Base grid is built once per room (room boundary only).
    Per pair: copy base grid, mark all other furniture as obstacles,
    find nearest free cell if centroid is blocked, then run A*.
    """
    rooms = {
        (r.get("id") or r.get("name")): r
        for r in layout.get("rooms", [])
        if r.get("geometry")
    }
    objects = layout.get("objects") or layout.get("furniture") or []

    # Group objects by roomId so we build one base grid per room
    by_room: dict[str, list] = {}
    for obj in objects:
        rid = obj.get("attributes", {}).get("roomId") or obj.get("roomId")
        if rid:
            by_room.setdefault(rid, []).append(obj)

    pairs: list[dict] = []
    worst_case: dict = {"from": None, "to": None, "distance": 0.0}

    for rid, objs in by_room.items():
        if len(objs) < 2:
            continue
        room = rooms.get(rid)
        if not room:
            continue

        room_poly = _make_polygon(room["geometry"])

        # Build base grid once for this room — room boundary only, no furniture
        base_grid, origin_x, origin_y, cols, rows = _build_grid(room_poly)

        for i, src_obj in enumerate(objs):
            for tgt_obj in objs[i + 1:]:
                if not src_obj.get("geometry") or not tgt_obj.get("geometry"):
                    continue

                src_label = src_obj.get("id") or src_obj.get("name") or "obj"
                tgt_label = tgt_obj.get("id") or tgt_obj.get("name") or "obj"

                # Copy base grid and mark all furniture except src and tgt as obstacles
                pair_grid = [row[:] for row in base_grid]
                for obj in objs:
                    if obj is src_obj or obj is tgt_obj:
                        continue
                    if obj.get("geometry"):
                        _mark_obstacles(
                            pair_grid, _make_polygon(obj["geometry"]),
                            origin_x, origin_y, cols, rows,
                        )

                # Get centroid cells; spiral outward if centroid lands on an obstacle
                src_pt = _interior_point(src_obj["geometry"])
                tgt_pt = _interior_point(tgt_obj["geometry"])
                src_raw = _world_to_cell(*src_pt, origin_x, origin_y, cols, rows)
                tgt_raw = _world_to_cell(*tgt_pt, origin_x, origin_y, cols, rows)
                src_cell = _nearest_free_cell(pair_grid, rows, cols, *src_raw)
                tgt_cell = _nearest_free_cell(pair_grid, rows, cols, *tgt_raw)

                if src_cell is None or tgt_cell is None:
                    pairs.append({
                        "source": src_label, "target": tgt_label,
                        "path": [], "steps": 0, "distance": 0.0,
                        "status": "unreachable",
                    })
                    continue

                cell_path, cell_dist = _astar(pair_grid, rows, cols, src_cell, tgt_cell)

                if cell_path is None:
                    pairs.append({
                        "source": src_label, "target": tgt_label,
                        "path": [], "steps": 0, "distance": 0.0,
                        "status": "unreachable",
                    })
                else:
                    real_dist = round(cell_dist * GRID_RESOLUTION, 3)
                    # Path reports start/end labels; full grid cell sequence omitted for brevity
                    pairs.append({
                        "source": src_label, "target": tgt_label,
                        "path": [src_label, tgt_label],
                        "steps": len(cell_path),
                        "distance": real_dist,
                        "status": "reachable",
                    })
                    if real_dist > worst_case["distance"]:
                        worst_case = {"from": src_label, "to": tgt_label, "distance": real_dist}

    return {"pairs": pairs, "worst_case": worst_case}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def check_paths(layout: dict[str, Any]) -> dict[str, Any]:
    """
    Auto-detect mode and run pathfinding.
    Mode 1 (no furniture): BFS between all room pairs via door graph.
    Mode 2 (furniture present): A* on per-room grid between object centroids.
    """
    if _has_furniture(layout):
        return _run_mode2(layout)
    return _run_mode1(layout)


# ---------------------------------------------------------------------------
# LangGraph node — same pattern as visibility.py
# ---------------------------------------------------------------------------

def build_path_node(mcp_client):
    """Return a path analysis node ready to be added to a LangGraph StateGraph."""

    def path_node(state):
        # Returns an update dict instead of mutating state.

        print("Running path analysis...")
        try:
            layout = json.loads(state["layout_json_string"])
            results = check_paths(layout)
        except Exception as exc:
            print(f"[path] Analysis failed: {exc}")
            results = {"pairs": [], "worst_case": {"from": None, "to": None, "distance": 0.0}}
        results_json = json.dumps(results)

        print(f"  {len(results.get('pairs', []))} pairs checked.")

        try:
            tool_output = mcp_client.call_tool("visualize_paths", {
                "layout_json": state["layout_json_string"],
                "paths_json": results_json,
            })
        except Exception as e:
            tool_output = f"visualize_paths error: {e}"

        print(f"Path tool result: {str(tool_output)[:500]}")

        return {
            "path_results": results,
            "messages": [
                {
                    "role": "assistant",
                    "content": json.dumps({
                        "action": "tool",
                        "final_response": "",
                        "tool_calls": [{"name": "visualize_paths", "arguments": {
                            "pairs_checked": len(results.get("pairs", [])),
                        }}],
                    }),
                },
                {
                    "role": "user",
                    "content": f"Tool result: {str(tool_output)[:500]}",
                },
            ],
        }

    return path_node
