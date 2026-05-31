from __future__ import annotations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from graph import AgentState

MAX_ADJUSTMENTS = 3  # Max times the graph loops back to reason for collision/reachability fixes


def analysis_fan_out_node(state: AgentState) -> dict:
    """No-op pass-through that exists solely as a fan-out point.
    LangGraph needs a single source node to fan out to the three
    Group 1 analysis nodes (collision, visibility, orientation).
    Returns an empty update dict — nothing to change in state."""
    return {}


def group1_join_node(state: AgentState) -> dict:
    """Join point after Group 1 parallel nodes converge.
    Increments adjustment_count so the router can enforce the max limit.
    LangGraph waits for all incoming edges (collision, visibility,
    orientation) to complete before executing this node."""
    collision = state.get("collision_results")
    if collision and not collision.get("pass", True):
        hard = collision.get("summary", {}).get("hard_violations", 0)
        if hard > 0 and state.get("last_placement_result") is not None:
            adj = state.get("adjustment_count", 0)

            # Build a forceful repositioning instruction so the LLM knows
            # exactly what to do when reason receives control back.
            # Without this message the LLM has no signal to reposition —
            # it just calls whatever tool it last used (visualize_paths).
            summary   = collision.get("summary", {})
            blocked   = summary.get("blocked_area_m2", 0)
            space_cfg = state.get("space_config") or {}
            clearance = space_cfg.get("clearance", 1.20)

            # Extract the name of the last placed object for the message
            history = state.get("placement_history") or []
            if history:
                last = history[-1]
                obj_name = last.get("name", "the object")
                last_x   = last.get("to", [0, 0])[0]
                last_y   = last.get("to", [0, 0])[1]
                position_hint = f"It is currently at ({last_x}, {last_y})."
            else:
                obj_name     = "the last placed object"
                position_hint = ""


            reposition_msg = (
                f"COLLISION VIOLATION — ADJUSTMENT REQUIRED ({adj + 1}/{MAX_ADJUSTMENTS}).\n"
                f"Blocked area: {blocked:.1f}m² — this must be reduced.\n"
                f"{position_hint}\n"
                f"Required clearance: {clearance}m on all sides.\n\n"
                f"You MUST call move_object for '{obj_name}' with NEW coordinates.\n"
                f"Move it at least {clearance + 0.5:.1f}m away from its current position.\n"
                f"Check room geometry carefully — stay away from walls, doors, and existing furniture.\n"
                f"Do NOT call visualize_paths, place_object, or any other tool.\n"
                f"Call move_object NOW with object_name='{obj_name}' and new x,y coordinates."
            )

            return {
                "adjustment_count": adj + 1,
                "messages": [{"role": "user", "content": reposition_msg}],
            }
    return {}
