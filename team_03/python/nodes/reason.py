"""
nodes/reason.py — LLM reasoning node: decides what to do next each turn.

The reason node is the brain of the agent. It reads the full conversation
history (including all tool results so far) and decides whether to:
  - Place an object  → sets object_to_place, routes to add_objects
  - Call a tool      → sets pending_tool_calls, routes to tools.py
  - Finish           → sets final_response, ends the current loop

No Rhino. No MCP calls. Pure LLM inference.
"""

from __future__ import annotations
from typing import Any
from _runtime.llm import call_llm
from prompts import SYSTEM_PROMPT, SPACE_CONTEXT_TEMPLATE, PROFILE_CONTEXT_TEMPLATE


# ---------------------------------------------------------------------------
# Reason node — the LLM decision step in the graph.
# ---------------------------------------------------------------------------

def build_reason_node(llm: Any):
    """Return a reason node ready to be added to a LangGraph StateGraph."""

    def reason_node(state: dict) -> dict:
        # If populate_agent filled the queue, skip the LLM entirely.
        # Just signal _route_after_reason to drain the queue via add_objects.
        queue = state.get("object_queue") or []
        object_to_place = state.get("object_to_place")
        if queue and not object_to_place:
            print(f"[reason] Queue has {len(queue)} objects — skipping LLM, draining queue.")
            return {
                "object_to_place":    queue[0],
                "object_queue":       queue[1:],
                "final_response":     "",
                "pending_tool_calls": [],
                "adjustment_count":   0,
            }

        print("\nReasoning with LLM...")

        # Pull space and profile config set by the pre-agents.
        # Both are None on the very first turn if the pre-agents haven't run,
        # so default to empty dict to keep the f-string logic below safe.
        space_config   = state.get("space_config")   or {}
        profile_config = state.get("profile_config") or {}

        # Build a compact context string from pre-agent outputs.
        # Prepended as a user message rather than baked into the system prompt
        # so it persists in conversation history and the LLM can see it across
        # turns — system prompts are not always echoed back in multi-turn calls.
        context_injection = ""
        if space_config:
            context_injection += SPACE_CONTEXT_TEMPLATE.format(
                space_type           = space_config.get("space_type", "unknown"),
                clearance            = space_config.get("clearance", 0.9),
                priorities           = space_config.get("priorities", []),
                use_clearance        = space_config.get("use_clearance", True),
                orientation_required = space_config.get("orientation_required", False),
            )
        if profile_config:
            context_injection += PROFILE_CONTEXT_TEMPLATE.format(
                profile_type      = profile_config.get("profile_type", "standard"),
                min_path_width    = profile_config.get("min_path_width", 0.9),
                turning_radius    = profile_config.get("turning_radius", 0.75),
                reach_height_min  = profile_config.get("reach_height_min", 0.4),
                reach_height_max  = profile_config.get("reach_height_max", 1.8),
            )

        # Inject spatial graph text so the LLM sees current relationships,
        # violations, and move vectors on every reasoning turn.
        graph_text = state.get("spatial_graph_text")
        if graph_text:
            context_injection += f"\nSPATIAL RELATIONSHIP GRAPH:\n{graph_text}\n"

        # Build a local message list — never mutate state["messages"] here.
        # The context block prepends so it appears before the user's request
        # in every LLM call without accumulating in the persistent history.
        messages = state["messages"]
        if context_injection:
            messages = [{"role": "user", "content": context_injection}] + messages

        import time as _time
        result = None
        _max_retries = 3
        for _attempt in range(1, _max_retries + 1):
            try:
                result = call_llm(llm, SYSTEM_PROMPT, messages, state["tool_catalog"])
                break
            except Exception as exc:
                print(f"[reason] LLM call failed (attempt {_attempt}/{_max_retries}): {exc}")
                if _attempt < _max_retries:
                    _wait = _attempt * 5  # 5s, 10s
                    print(f"[reason] Retrying in {_wait}s...")
                    _time.sleep(_wait)
                else:
                    return {
                        "final_response": f"LLM error after {_max_retries} attempts: {exc}",
                        "pending_tool_calls": [],
                        "object_to_place": {},
                    }

        # Build an update dict — never mutate state directly.
        updates: dict = {}

        if result["action"] == "query":
            updates["_query_mode"] = True
            updates["object_to_place"] = {}
            updates["pending_tool_calls"] = []
            updates["final_response"] = ""

        elif result["action"] == "final":
            # LLM is done — store the response and clear any queued tool calls.
            # Use empty containers ({} / []) instead of None to clear fields:
            # _keep_last treats None as "no update" and preserves the old value.
            updates["final_response"] = result["final_response"]
            updates["pending_tool_calls"] = []
            updates["object_to_place"] = {}
            updates["_query_mode"] = False

        else:
            # LLM wants to call tools — split place_object from everything else.
            #
            # place_object is intercepted here rather than in tools.py because
            # it needs a different execution path: the graph routes to add_objects,
            # which handles MCP communication and workspace file persistence.
            # Generic analysis tools go through tools.py, which is stateless and
            # simply fires the MCP call and returns the result string.
            # Splitting at the reason node keeps each downstream node focused on
            # one responsibility and avoids branching logic inside tools.py.
            tool_calls   = result.get("tool_calls", [])
            # Accept both spellings — the LLM sometimes outputs "place_objects"
            # (matching the MCP tool name) instead of "place_object".
            place_names  = {"place_object", "place_objects"}
            place_calls  = [t for t in tool_calls if t["name"] in place_names]
            other_calls  = [t for t in tool_calls if t["name"] not in place_names]

            if place_calls:
                # Signal the graph to route to add_objects on the next edge.
                # Only the first place_object call is taken per turn so the LLM
                # can review analysis results before placing the next object.
                updates["object_to_place"] = place_calls[0]["arguments"]
                print(f"Placing object: {place_calls[0]['arguments'].get('objects_list', '')}")
                if len(place_calls) > 1:
                    updates["object_queue"] = [c["arguments"] for c in place_calls[1:]]
                    print(f"[reason] Queued {len(place_calls) - 1} additional object(s)")
                # Do NOT clear object_queue here — populate_agent may have filled it.
                # Only overwrite if the LLM explicitly queued more objects.
            else:
                # Clear with {} — _keep_last treats None as "no update" and
                # would preserve the stale value from a previous placement.
                updates["object_to_place"] = {}
                # Do NOT clear object_queue — preserve populate_agent queue.

            # Pass any non-placement tool calls to tools.py as normal.
            # Use [] instead of None so _keep_last actually clears the field.
            updates["pending_tool_calls"] = other_calls if other_calls else []
            updates["_query_mode"] = False

            # Clear stale final_response so the routing function doesn't
            # mistake a value from a previous turn as "finish".
            # Use empty string instead of None — the _keep_last reducer treats
            # None as "no update" and would preserve the stale value.
            updates["final_response"] = ""

        return updates

    return reason_node
