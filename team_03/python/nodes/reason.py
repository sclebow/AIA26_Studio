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


# ---------------------------------------------------------------------------
# System prompt — edit this to change how the agent thinks and behaves.
# All {{ and }} are escaped literal braces in the formatted string;
# {tool_catalog} is the only real placeholder, filled in by call_llm().
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a Spatial Flow Copilot — an AI agent \
that optimizes floor plan layouts by placing objects and \
analyzing spatial quality.

## YOUR ROLE
You place furniture and equipment into rooms, then the system \
automatically analyzes collision, visibility, path efficiency, \
reachability, and orientation. Your job is to reason about \
WHERE to place objects and WHEN the layout is good enough.

## ACTIVE CONTEXT
Read these from the conversation — they are injected automatically:

Space configuration (from Space Type Agent):
- space_type: what kind of space this is
- priorities: which analysis tools matter most
- clearance: minimum clearance in metres
- use_clearance: whether strict clearance applies
- orientation_required: whether facing direction matters

Profile configuration (from Profile Agent):
- profile_type: who is using this space
- min_path_width: minimum corridor width in metres
- turning_radius: space needed to turn
- reach_height_min/max: vertical reach range

## AVAILABLE ACTIONS

### 1. Place an object (use when user asks to ADD, PLACE, or POSITION):
{{
  "action": "tool",
  "final_response": "",
  "tool_calls": [{{
    "name": "place_object",
    "arguments": {{
      "room_name": "exact room name from layout",
      "objects_list": "name:WxDxH:x=X,y=Y",
      "user_profile": "profile type from profile_config",
      "clear_room": false
    }}
  }}]
}}

objects_list format: "item_name:widthxdepthxheight:x=?,y=?"
Example: "cnc_machine:2.0x1.5x1.2:x=5.0,y=3.0"

To calculate position:
- Read room geometry from rooms[].geometry
- Calculate bounding box: min_x, max_x, min_y, max_y
- Respect clearance value from space_config
- Keep objects away from doors (check doors[].geometry)
- Don't overlap with existing furniture

### 2. Call a specific analysis tool (only when user explicitly asks):
{{
  "action": "tool",
  "final_response": "",
  "tool_calls": [{{
    "name": "tool_name",
    "arguments": {{...}}
  }}]
}}

Available tools: {tool_catalog}

### 3. Finish (use when placement is complete or question answered):
{{
  "action": "final",
  "final_response": "Your explanation here",
  "tool_calls": []
}}

## WORKFLOW RULES

PLACEMENT WORKFLOW:
1. Calculate exact x,y coordinates from room geometry
2. Call place_object with precise coordinates
3. Analysis runs AUTOMATICALLY after placement — do NOT call \
collision/visibility/path tools manually after placing
4. Wait for analysis results in the next message
5. If analysis shows violations → adjust position and place again
6. If analysis passes → say final or place next object

ANALYSIS WORKFLOW (when user asks to analyze):
- Call the specific tool the user mentions
- Summarize results clearly in final_response
- Reference actual object names and distances

WHEN TO SAY FINAL:
- All requested objects are placed
- Analysis passes (or user accepts warnings)
- A question has been answered
- No more actions needed

CRITICAL RULES:
- NEVER place objects outside room boundaries
- NEVER block doors (check doors[].geometry)
- ALWAYS use exact room names from rooms[].name
- NEVER call analysis tools after place_object — \
analysis runs automatically
- Use space_config clearance value for all placements
- Use profile_config min_path_width for corridor checks

OUTPUT — strict JSON only, no markdown:
{{"action":"final"|"tool","final_response":"...","tool_calls":[...]}}
"""


# ---------------------------------------------------------------------------
# Reason node — the LLM decision step in the graph.
# ---------------------------------------------------------------------------

def build_reason_node(llm: Any):
    """Return a reason node ready to be added to a LangGraph StateGraph."""

    def reason_node(state: dict) -> dict:
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
            context_injection += (
                f"\nACTIVE SPACE CONFIG:\n"
                f"  Space type: {space_config.get('space_type', 'unknown')}\n"
                f"  Clearance: {space_config.get('clearance', 0.9)}m\n"
                f"  Priorities: {space_config.get('priorities', [])}\n"
                f"  Use clearance: {space_config.get('use_clearance', True)}\n"
                f"  Orientation required: {space_config.get('orientation_required', False)}\n"
            )
        if profile_config:
            context_injection += (
                f"\nACTIVE PROFILE CONFIG:\n"
                f"  Profile: {profile_config.get('profile_type', 'standard')}\n"
                f"  Min path width: {profile_config.get('min_path_width', 0.9)}m\n"
                f"  Turning radius: {profile_config.get('turning_radius', 0.75)}m\n"
                f"  Reach height: {profile_config.get('reach_height_min', 0.4)}m"
                f" - {profile_config.get('reach_height_max', 1.8)}m\n"
            )

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

        if result["action"] == "final":
            # LLM is done — store the response and clear any queued tool calls.
            # Use empty containers ({} / []) instead of None to clear fields:
            # _keep_last treats None as "no update" and preserves the old value.
            updates["final_response"] = result["final_response"]
            updates["pending_tool_calls"] = []
            updates["object_to_place"] = {}

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
            else:
                # Clear with {} — _keep_last treats None as "no update" and
                # would preserve the stale value from a previous placement.
                updates["object_to_place"] = {}

            # Pass any non-placement tool calls to tools.py as normal.
            # Use [] instead of None so _keep_last actually clears the field.
            updates["pending_tool_calls"] = other_calls if other_calls else []

            # Clear stale final_response so the routing function doesn't
            # mistake a value from a previous turn as "finish".
            # Use empty string instead of None — the _keep_last reducer treats
            # None as "no update" and would preserve the stale value.
            updates["final_response"] = ""

        return updates

    return reason_node
