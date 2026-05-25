"""
nodes/visibility.py — Line-of-sight analysis between rooms (Mode 1) and objects (Mode 2).

Mode 1 (no objects): centroid of source room → centroid of target room
Mode 2 (objects placed): object use_point → object functional_point

Requires: shapely
"""

from __future__ import annotations
import json
from typing import Any
from shapely.geometry import LineString, Point, Polygon

SEATED_HEIGHT = 0.9
STANDING_HEIGHT = 1.6
DOOR_TOLERANCE = 0.3  # metres — crossing must be this close to a door to count as open


def _make_polygon(pts: list) -> Polygon:
    return Polygon(pts)


def _centroid(pts: list) -> tuple[float, float]:
    p = _make_polygon(pts)
    return (p.centroid.x, p.centroid.y)


def _resolve_use_pt(obj: dict) -> tuple[float, float] | None:
    """use_point → geometry centroid → position."""
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
    """functional_point → use_point (with its own fallbacks)."""
    pt = obj.get("functional_point")
    if pt:
        return tuple(pt[:2])
    return _resolve_use_pt(obj)


def _near_door(pt: Point, doors: list[dict]) -> bool:
    """True if pt is within DOOR_TOLERANCE of any door position or geometry."""
    for door in doors:
        pos = door.get("position")
        if pos and pt.distance(Point(pos[:2])) < DOOR_TOLERANCE:
            return True
        geom = door.get("geometry")
        if geom and len(geom) == 2 and pt.distance(LineString(geom)) < DOOR_TOLERANCE:
            return True
    return False


def _wall_segments(rooms: list[dict]):
    """Yield (segment, room_label) for every non-degenerate edge of each room polygon."""
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


def _find_blocker(
    ray: LineString,
    rooms: list[dict],
    doors: list[dict],
    src_label: str,
    tgt_label: str,
) -> str | None:
    """Return label of the first wall the ray crosses that is not the source/target room or a door."""
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


def _check_sightline(
    src: tuple[float, float],
    tgt: tuple[float, float],
    rooms: list[dict],
    doors: list[dict],
    src_label: str,
    tgt_label: str,
) -> dict[str, Any]:
    ray = LineString([src, tgt])
    blocked_by = _find_blocker(ray, rooms, doors, src_label, tgt_label)
    return {
        "source": src_label,
        "target": tgt_label,
        # Both heights share the same 2D ray; will diverge once 3D wall heights are introduced
        "visible_seated": blocked_by is None,
        "visible_standing": blocked_by is None,
        "blocked_by": blocked_by,
    }


def check_visibility(layout: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Check line-of-sight between objects sharing the same roomId.
    Returns empty list if no objects are placed in the layout.
    """
    rooms = layout.get("rooms", [])
    doors = layout.get("doors", [])
    objects = layout.get("objects") or layout.get("furniture") or []

    if not objects:
        return []  # no objects placed — nothing to check

    results = []
    for i, src_obj in enumerate(objects):
        for tgt_obj in objects[i + 1:]:
            src_room = src_obj.get("attributes", {}).get("roomId")
            tgt_room = tgt_obj.get("attributes", {}).get("roomId")
            if not src_room or not tgt_room or src_room != tgt_room:
                continue  # skip cross-room pairs
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


def build_visibility_node(mcp_client):
    """Return a visibility node ready to be added to a LangGraph StateGraph."""

    def visibility_node(state):
        # Parallel-safe: returns an update dict instead of mutating state.
        # Do NOT increment iteration — parallel nodes share the counter and
        # the _keep_last reducer would silently drop increments from siblings.

        print("Running visibility analysis...")
        try:
            layout = json.loads(state["layout_json_string"])
            results = check_visibility(layout)
        except Exception as exc:
            print(f"[visibility] Analysis failed: {exc}")
            results = []
        visibility_json = json.dumps(results)

        print(f"  {len(results)} pairs checked.")

        try:
            tool_output = mcp_client.call_tool("visualize_visibility", {
                "layout_json": state["layout_json_string"],
                "visibility_json": visibility_json,
            })
        except Exception as e:
            tool_output = f"visualize_visibility error: {e}"

        print(f"Visibility tool result: {str(tool_output)[:500]}")

        # Return partial update — LangGraph merges via add_messages / _keep_last.
        return {
            "visibility_results": results,
            "messages": [
                {
                    "role": "assistant",
                    "content": json.dumps({
                        "action": "tool",
                        "final_response": "",
                        "tool_calls": [{"name": "visualize_visibility", "arguments": {"pairs_checked": len(results)}}],
                    }),
                },
                {
                    "role": "user",
                    "content": f"Tool result: {str(tool_output)[:500]}",
                },
            ],
        }

    return visibility_node
