"""
nodes/reachability.py — Ergonomic reachability analysis for furniture/objects.

For each object in the layout:
  - Resolves use_point (where a person stands/sits) and functional_point
    (the point they need to reach — e.g. a button, shelf, screen).
  - Estimates functional_point height from the object type name if no z is given.
  - Checks if the functional_point is within the user's reach envelope:
      height_ok:  z within [reach_height_min, reach_height_max]
      radius_ok:  2D distance from use_point to functional_point <= reach_radius
  - reachable = height_ok AND radius_ok

Requires: shapely
"""

from __future__ import annotations
import json
import math
from typing import Any

from shapely.geometry import Polygon

DEFAULT_PROFILE = {
    "reach_height_min": 0.4,
    "reach_height_max": 1.8,
    "reach_radius": 0.7,
    "seated_height": 0.9,
}

# Keyword tuples mapped to estimated functional height in metres
_TYPE_HEIGHT: list[tuple[tuple[str, ...], float]] = [
    (("shelf", "rack"),              1.6),
    (("table", "desk", "counter"),   0.85),
    (("machine", "cnc", "conveyor"), 1.0),
]
_DEFAULT_HEIGHT = 0.9


def _centroid(pts: list) -> tuple[float, float]:
    p = Polygon(pts)
    c = p.centroid
    return (c.x, c.y)


def _resolve_use_pt(obj: dict) -> tuple[float, float] | None:
    """use_point -> geometry centroid -> position (same chain as visibility.py)."""
    pt = obj.get("use_point")
    if pt:
        return (pt[0], pt[1])
    geom = obj.get("geometry")
    if geom:
        return _centroid(geom)
    pt = obj.get("position")
    if pt:
        return (pt[0], pt[1])
    return None


def _resolve_functional_pt(obj: dict) -> tuple[float, float] | None:
    """functional_point -> use_point fallbacks."""
    pt = obj.get("functional_point")
    if pt:
        return (pt[0], pt[1])
    return _resolve_use_pt(obj)


def _functional_height(obj: dict) -> float:
    """
    Use z from functional_point if available.
    Otherwise estimate from keywords in object type or name.
    """
    fp = obj.get("functional_point")
    if fp and len(fp) >= 3:
        return float(fp[2])
    type_str = (obj.get("type") or obj.get("name") or "").lower()
    for keywords, height in _TYPE_HEIGHT:
        if any(kw in type_str for kw in keywords):
            return height
    return _DEFAULT_HEIGHT


def _euclidean_2d(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def check_reachability(
    layout: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Check ergonomic reachability for every furniture/object in the layout.
    Returns {"results": [...], "summary": {...}}.
    """
    p = {**DEFAULT_PROFILE, **(profile or {})}
    objects = layout.get("objects") or layout.get("furniture") or []

    results: list[dict] = []
    unreachable_names: list[str] = []

    for obj in objects:
        obj_id   = obj.get("id")   or obj.get("name") or "unknown"
        obj_name = obj.get("name") or obj_id

        use_pt  = _resolve_use_pt(obj)
        func_pt = _resolve_functional_pt(obj)

        if use_pt is None or func_pt is None:
            # No geometry or position data — cannot analyse
            results.append({
                "object_id": obj_id, "name": obj_name,
                "reachable": False, "height_ok": False, "radius_ok": False,
                "functional_point_height": None, "distance_to_functional": None,
            })
            unreachable_names.append(obj_name)
            continue

        height = _functional_height(obj)
        dist   = _euclidean_2d(use_pt, func_pt)

        # height_ok: functional point z is within standing reach envelope
        # radius_ok: horizontal distance from use_point to functional_point xy
        height_ok = p["reach_height_min"] <= height <= p["reach_height_max"]
        radius_ok = dist <= p["reach_radius"]
        reachable = height_ok and radius_ok

        if not reachable:
            unreachable_names.append(obj_name)

        results.append({
            "object_id": obj_id, "name": obj_name,
            "reachable": reachable,
            "height_ok": height_ok,
            "radius_ok": radius_ok,
            "functional_point_height": round(height, 3),
            "distance_to_functional":  round(dist, 3),
        })

    n_reachable = sum(1 for r in results if r["reachable"])
    summary = {
        "total":               len(results),
        "reachable":           n_reachable,
        "unreachable":         len(results) - n_reachable,
        "unreachable_objects": unreachable_names,
    }

    return {"results": results, "summary": summary}


def build_reachability_node(mcp_client):
    """Return a reachability node ready to be added to a LangGraph StateGraph."""

    def reachability_node(state):
        # Returns an update dict instead of mutating state.

        print("Running reachability analysis...")
        try:
            layout  = json.loads(state["layout_json_string"])
            profile = state.get("profile_config")
            output  = check_reachability(layout, profile)
        except Exception as exc:
            print(f"[reachability] Analysis failed: {exc}")
            output = {"results": [], "summary": {"total": 0, "reachable": 0, "unreachable": 0, "unreachable_objects": []}}
        summary = output["summary"]

        print(
            f"  {summary['reachable']}/{summary['total']} objects reachable."
        )

        # Placeholder — visualize_reachability not yet implemented in GH MCP server
        print("visualize_reachability: placeholder (MCP tool not yet available)")

        return {
            "reachability_results": output,
            "messages": [
                {
                    "role": "assistant",
                    "content": json.dumps({
                        "action": "tool",
                        "final_response": "",
                        "tool_calls": [{"name": "visualize_reachability", "arguments": {
                            "total":     summary["total"],
                            "reachable": summary["reachable"],
                        }}],
                    }),
                },
                {
                    "role": "user",
                    "content": "Tool result: visualize_reachability placeholder",
                },
            ],
        }

    return reachability_node
