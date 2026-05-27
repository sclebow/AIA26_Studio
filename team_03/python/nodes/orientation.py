"""
nodes/orientation.py — Facing direction analysis for furniture/objects.

For each object in the layout that has an 'orientation' field:
  - Resolves the facing direction (angle in degrees or [x, y] vector).
  - Resolves the target direction from:
      target_direction: explicit angle or [x, y] vector
      target: [x, y] point or object id — angle computed from use_point to target
  - Computes angle_diff between facing and target, normalised to [0, 180].
  - facing_ok = angle_diff <= tolerance_degrees

Objects without an orientation field are skipped entirely.
Objects with orientation but no resolvable target are counted as skipped.

Requires: math (stdlib only)
"""

from __future__ import annotations
import json
import math
from typing import Any

DEFAULT_CONFIG = {
    "tolerance_degrees": 45,
}


def _resolve_use_pt(obj: dict) -> tuple[float, float] | None:
    """use_point -> geometry centroid -> position."""
    pt = obj.get("use_point")
    if pt:
        return (pt[0], pt[1])
    geom = obj.get("geometry")
    if geom:
        xs = [p[0] for p in geom]
        ys = [p[1] for p in geom]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    pt = obj.get("position")
    if pt:
        return (pt[0], pt[1])
    return None


def _to_angle(value) -> float | None:
    """
    Convert an orientation value to degrees.
    Accepts a number (already degrees) or [x, y] vector (atan2).
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return math.degrees(math.atan2(value[1], value[0]))
    return None


def _angle_diff(a: float, b: float) -> float:
    """Absolute angular difference in degrees, normalised to [0, 180]."""
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


def _build_obj_index(objects: list[dict]) -> dict[str, dict]:
    """Lookup dict from object id and name to object, for target resolution."""
    index: dict[str, dict] = {}
    for obj in objects:
        if obj.get("id"):
            index[obj["id"]] = obj
        if obj.get("name"):
            index[obj["name"]] = obj
    return index


def _resolve_target_angle(obj: dict, obj_index: dict[str, dict]) -> float | None:
    """
    Resolve target direction angle (degrees) for an object. Checks in order:
      1. target_direction field (angle or vector)
      2. target as [x, y] point  -> angle from use_point to target
      3. target as object id/name -> angle from use_point to target's use_point
    Returns None if no target can be resolved.
    """
    td = obj.get("target_direction")
    if td is not None:
        angle = _to_angle(td)
        if angle is not None:
            return angle

    target = obj.get("target")
    if target is None:
        return None

    use_pt = _resolve_use_pt(obj)
    if use_pt is None:
        return None

    # Target as explicit [x, y] coordinate
    if isinstance(target, (list, tuple)) and len(target) >= 2:
        dx, dy = target[0] - use_pt[0], target[1] - use_pt[1]
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return None  # same point — direction undefined
        return math.degrees(math.atan2(dy, dx))

    # Target as object id or name string
    if isinstance(target, str):
        target_obj = obj_index.get(target)
        if target_obj is None:
            return None
        target_pt = _resolve_use_pt(target_obj)
        if target_pt is None:
            return None
        dx, dy = target_pt[0] - use_pt[0], target_pt[1] - use_pt[1]
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return None
        return math.degrees(math.atan2(dy, dx))

    return None


def check_orientation(
    layout: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Check facing direction for every object that has an 'orientation' field.
    Returns {"results": [...], "summary": {...}}.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    tolerance = cfg["tolerance_degrees"]

    objects = layout.get("objects") or layout.get("furniture") or []
    obj_index = _build_obj_index(objects)

    results: list[dict] = []
    wrong_names: list[str] = []
    skipped = 0

    for obj in objects:
        # Only analyse objects that declare an orientation
        if "orientation" not in obj:
            continue

        obj_id   = obj.get("id")   or obj.get("name") or "unknown"
        obj_name = obj.get("name") or obj_id

        orientation_deg = _to_angle(obj["orientation"])
        if orientation_deg is None:
            skipped += 1
            continue

        target_deg = _resolve_target_angle(obj, obj_index)
        if target_deg is None:
            skipped += 1
            continue

        diff = _angle_diff(orientation_deg, target_deg)
        facing_ok = diff <= tolerance

        if not facing_ok:
            wrong_names.append(obj_name)

        results.append({
            "object_id":            obj_id,
            "name":                 obj_name,
            "facing_ok":            facing_ok,
            "angle_diff":           round(diff, 2),
            "orientation_deg":      round(orientation_deg, 2),
            "target_direction_deg": round(target_deg, 2),
        })

    n_ok = sum(1 for r in results if r["facing_ok"])
    summary = {
        "total":         len(results),
        "facing_ok":     n_ok,
        "facing_wrong":  len(results) - n_ok,
        "skipped":       skipped,
        "wrong_objects": wrong_names,
    }

    return {"results": results, "summary": summary}


def build_orientation_node(mcp_client):
    """Return an orientation node ready to be added to a LangGraph StateGraph."""

    def orientation_node(state):
        # Parallel-safe: returns an update dict instead of mutating state.
        # Do NOT increment iteration — parallel nodes share the counter and
        # the _keep_last reducer would silently drop increments from siblings.

        print("Running orientation analysis...")
        try:
            layout  = json.loads(state["layout_json_string"])
            output  = check_orientation(layout)
        except Exception as exc:
            print(f"[orientation] Analysis failed: {exc}")
            output = {"results": [], "summary": {"total": 0, "facing_ok": 0, "facing_wrong": 0, "skipped": 0, "wrong_objects": []}}
        summary = output["summary"]

        print(
            f"  {summary['facing_ok']}/{summary['total']} objects correctly oriented "
            f"({summary['skipped']} skipped)."
        )

        # Placeholder — visualize_orientation not yet implemented in GH MCP server
        print("visualize_orientation: placeholder (MCP tool not yet available)")

        # Return partial update — LangGraph merges via add_messages / _keep_last.
        return {
            "orientation_results": output,
            "messages": [
                {
                    "role": "assistant",
                    "content": json.dumps({
                        "action": "tool",
                        "final_response": "",
                        "tool_calls": [{"name": "visualize_orientation", "arguments": {
                            "total":     summary["total"],
                            "facing_ok": summary["facing_ok"],
                            "skipped":   summary["skipped"],
                        }}],
                    }),
                },
                {
                    "role": "user",
                    "content": "Tool result: visualize_orientation placeholder",
                },
            ],
        }

    return orientation_node
