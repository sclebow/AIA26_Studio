"""
nodes/visibility.py — Line-of-sight analysis between rooms (Mode 1) and objects (Mode 2).

Mode 1 (no objects): centroid of source room → centroid of target room
Mode 2 (objects placed): object use_point → object functional_point

Also computes per-object isovist polygons at two heights:
  SEATED_HEIGHT  = 0.9m  (work surface / seated eye level)
  STANDING_HEIGHT = 1.55m (standing eye level)

Requires: shapely
"""

from __future__ import annotations
import json
import math
from typing import Any
from shapely.geometry import LineString, Point, Polygon, MultiPolygon
from shapely.ops import unary_union

SEATED_HEIGHT   = 0.90
STANDING_HEIGHT = 1.55
DOOR_TOLERANCE  = 0.30   # metres
ISOVIST_RAYS    = 72     # every 5° — lightweight but accurate enough
ISOVIST_RADIUS  = 20.0   # max ray length in metres


def _make_polygon(pts: list) -> Polygon:
    return Polygon(pts)


def _centroid(pts: list) -> tuple[float, float]:
    p = _make_polygon(pts)
    return (p.centroid.x, p.centroid.y)


def _resolve_use_pt(obj: dict) -> tuple[float, float] | None:
    pt = obj.get("use_point")
    if pt:
        return tuple(pt[:2])
    geom = obj.get("geometry")
    if geom:
        return _centroid(geom)
    pt = obj.get("position")
    if pt:
        return tuple(pt[:2])
    return None


def _resolve_functional_pt(obj: dict) -> tuple[float, float] | None:
    pt = obj.get("functional_point")
    if pt:
        return tuple(pt[:2])
    return _resolve_use_pt(obj)


def _near_door(pt: Point, doors: list[dict]) -> bool:
    for door in doors:
        pos = door.get("position")
        if pos and pt.distance(Point(pos[:2])) < DOOR_TOLERANCE:
            return True
        geom = door.get("geometry")
        if geom and len(geom) == 2 and pt.distance(LineString(geom)) < DOOR_TOLERANCE:
            return True
    return False


def _wall_segments(rooms: list[dict]):
    for room in rooms:
        geom = room.get("geometry")
        if not geom:
            continue
        label = room.get("name") or room.get("id") or "wall"
        pts = geom if geom[0] == geom[-1] else geom + [geom[0]]
        for i in range(len(pts) - 1):
            seg = LineString([pts[i], pts[i + 1]])
            if seg.length > 0:
                yield seg, label


def _find_blocker(ray, rooms, doors, src_label, tgt_label):
    for seg, label in _wall_segments(rooms):
        if label == src_label or label == tgt_label:
            continue
        if not ray.crosses(seg):
            continue
        cross = ray.intersection(seg)
        if cross.is_empty:
            continue
        cross_pt = (
            Point(cross.x, cross.y)
            if hasattr(cross, "x")
            else Point(*list(cross.geoms)[0].coords[0])
        )
        if not _near_door(cross_pt, doors):
            return label
    return None


def _check_sightline(src, tgt, rooms, doors, src_label, tgt_label):
    ray = LineString([src, tgt])
    blocked_by = _find_blocker(ray, rooms, doors, src_label, tgt_label)
    return {
        "source":           src_label,
        "target":           tgt_label,
        "visible_seated":   blocked_by is None,
        "visible_standing": blocked_by is None,
        "blocked_by":       blocked_by,
    }


# ---------------------------------------------------------------------------
# Isovist computation
# ---------------------------------------------------------------------------

def _build_obstacle_segments(layout: dict) -> list:
    """
    Collect all line segments that block vision:
    - room boundary walls (not doors)
    - furniture footprint edges
    Returns list of shapely LineString.
    """
    segments = []
    rooms  = layout.get("rooms", [])
    doors  = layout.get("doors", [])
    objects = layout.get("furniture") or layout.get("objects") or []

    # Room walls — split at doors
    door_lines = [
        LineString(d["geometry"])
        for d in doors
        if len(d.get("geometry", [])) == 2
    ]
    for room in rooms:
        geom = room.get("geometry", [])
        if not geom:
            continue
        pts = geom if geom[0] == geom[-1] else geom + [geom[0]]
        for i in range(len(pts) - 1):
            seg = LineString([pts[i], pts[i + 1]])
            # Remove door openings from wall segment
            blocked = seg
            for dl in door_lines:
                try:
                    blocked = blocked.difference(dl.buffer(DOOR_TOLERANCE))
                except Exception:
                    pass
            if hasattr(blocked, "geoms"):
                for part in blocked.geoms:
                    if part.length > 0.01:
                        segments.append(part)
            elif blocked.length > 0.01:
                segments.append(blocked)

    # Furniture edges
    for furn in objects:
        geom = furn.get("geometry", [])
        if len(geom) >= 3:
            pts = geom if geom[0] == geom[-1] else geom + [geom[0]]
            for i in range(len(pts) - 1):
                seg = LineString([pts[i], pts[i + 1]])
                if seg.length > 0.01:
                    segments.append(seg)

    return segments


def compute_isovist(
    origin: tuple[float, float],
    obstacle_segments: list,
    num_rays: int = ISOVIST_RAYS,
    max_radius: float = ISOVIST_RADIUS,
) -> list[tuple[float, float]]:
    """
    Cast rays from origin in all directions.
    Returns polygon vertices of the visible area.
    """
    ox, oy = origin
    vertices = []

    for i in range(num_rays):
        angle = 2.0 * math.pi * i / num_rays
        dx = math.cos(angle) * max_radius
        dy = math.sin(angle) * max_radius
        ray = LineString([(ox, oy), (ox + dx, oy + dy)])

        min_t = 1.0  # parameter along ray (0=origin, 1=max_radius end)
        for seg in obstacle_segments:
            try:
                inter = ray.intersection(seg)
                if inter.is_empty:
                    continue
                # Get closest intersection point
                if hasattr(inter, "geoms"):
                    pts = list(inter.geoms)
                else:
                    pts = [inter]
                for pt in pts:
                    if hasattr(pt, "x"):
                        t = math.sqrt((pt.x - ox)**2 + (pt.y - oy)**2) / max_radius
                        if t < min_t:
                            min_t = t
            except Exception:
                continue

        hit_x = ox + dx * min_t
        hit_y = oy + dy * min_t
        vertices.append((round(hit_x, 3), round(hit_y, 3)))

    return vertices


def compute_isovists_for_layout(layout: dict) -> list[dict]:
    """
    Compute isovist polygon for each furniture object.
    Returns list of dicts with object id, name, origin, and polygon vertices.
    """
    objects   = layout.get("furniture") or layout.get("objects") or []
    obstacles = _build_obstacle_segments(layout)
    results   = []

    for obj in objects:
        origin = _resolve_use_pt(obj)
        if not origin:
            continue
        try:
            verts = compute_isovist(origin, obstacles)
            if len(verts) < 3:
                continue
            # Compute visible area
            poly = Polygon(verts)
            area = round(poly.area, 2) if poly.is_valid else 0.0
            results.append({
                "id":     obj.get("id", "unknown"),
                "name":   obj.get("name", "unknown"),
                "origin": list(origin),
                "polygon_seated":   verts,   # z = SEATED_HEIGHT in GH
                "polygon_standing": verts,   # same 2D, different z in GH
                "area_m2": area,
            })
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Main visibility check (unchanged)
# ---------------------------------------------------------------------------

def check_visibility(layout: dict[str, Any]) -> list[dict[str, Any]]:
    rooms   = layout.get("rooms", [])
    doors   = layout.get("doors", [])
    objects = layout.get("objects") or layout.get("furniture") or []

    if not objects:
        return []

    results = []
    for i, src_obj in enumerate(objects):
        for tgt_obj in objects[i + 1:]:
            src_room = src_obj.get("attributes", {}).get("roomId")
            tgt_room = tgt_obj.get("attributes", {}).get("roomId")
            if not src_room or not tgt_room or src_room != tgt_room:
                continue
            src_pt = _resolve_use_pt(src_obj)
            tgt_pt = _resolve_functional_pt(tgt_obj)
            if not src_pt or not tgt_pt:
                continue
            results.append(_check_sightline(
                src_pt, tgt_pt, rooms, doors,
                src_obj.get("id") or src_obj.get("name") or "obj",
                tgt_obj.get("id") or tgt_obj.get("name") or "obj",
            ))
    return results


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------

def build_visibility_node(mcp_client):

    def visibility_node(state):
        print("Running visibility analysis...")
        try:
            layout  = json.loads(state["layout_json_string"])
            results = check_visibility(layout)
            isovists = compute_isovists_for_layout(layout)
        except Exception as exc:
            print(f"[visibility] Analysis failed: {exc}")
            results  = []
            isovists = []

        print(f"  {len(results)} pairs checked.")

        visibility_json = json.dumps({
            "sightlines": results,
            "isovists":   isovists,
        })

        try:
            tool_output = mcp_client.call_tool("visualize_visibility", {
                "layout_json":     state["layout_json_string"],
                "visibility_json": visibility_json,
            })
        except Exception as e:
            tool_output = f"visualize_visibility error: {e}"

        print(f"Visibility tool result: {str(tool_output)[:500]}")

        return {
            "visibility_results": results,
            "messages": [
                {
                    "role": "assistant",
                    "content": json.dumps({
                        "action": "tool",
                        "final_response": "",
                        "tool_calls": [{"name": "visualize_visibility", "arguments": {
                            "pairs_checked": len(results),
                            "isovists":      len(isovists),
                        }}],
                    }),
                },
                {
                    "role": "user",
                    "content": f"Tool result: {str(tool_output)[:500]}",
                },
            ],
        }

    return visibility_node
