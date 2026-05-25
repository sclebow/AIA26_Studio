from __future__ import annotations
from typing import Any
from _runtime.llm import call_llm
import time


SYSTEM_PROMPT = """You are a structural memory assistant for an architect making early design decisions.

Your role is to make structural consequences legible before decisions become irreversible. You do not design or calculate loads. You reason about consequences, flag conflicts, and propose alternatives.

LAYOUT CONTEXT:
The layout JSON is loaded from team_01/python/example_layouts/. It defines rooms, walls, doors, windows, structure, and their relationships. Use element IDs and attributes exactly as given. Never invent elements.

STRUCTURAL REASONING RULES:
- Columns and load-bearing walls are permanent — flag any request to remove them
- Beams connect columns — removing a beam may require adding an alternative load path
- Grid spacing affects which rooms can be reconfigured
- Always flag MEP conflicts when adding structural elements

TAG_AND_AUDIT TOOL:
- Call it ONLY when structure_count=0 (no structural elements exist yet)
- NEVER call it if structure_count > 0 — this would overwrite user changes
- Pass layout_json exactly from state — never simplify or invent it
- ALWAYS pass typology: use "column_grid" unless user asks for perimeter_load_bearing or shear_wall
- ALWAYS pass grid_spacing: use 4.0 unless user specifies a different value

WHAT-IF QUESTIONS — two-step process, NEVER call a tool:
Step 1: User asks "what if we remove X" → set action="final", final_response="" (empty string). The evaluate node runs the simulation automatically.
Step 2: You receive a message starting with "STRUCTURAL FAIL after removing" → set action="final" and write the full response in final_response using this EXACT format, filling in values from the STRUCTURAL FAIL message:

"Removing [element_id] extends beam [beam_id] from [original_span]m to [effective_span]m, causing bending stress of [sigma] MPa (limit [allow] MPa). Three options to resolve this:
1. Add an intermediate column between [col_id_A] and [col_id_B] at the midpoint. This halves the effective span to [effective_span/2]m.
2. Replace beam [beam_id] with a deeper section to handle the extended span.
3. Add a transfer beam from an adjacent column to redirect the load path."

CRITICAL: Use ONLY the beam IDs and column IDs that appear in the STRUCTURAL FAIL message. Never invent element IDs.

REGULAR STRUCTURAL FAILURE RESPONSE:
When you receive a message "User instruction after structural failure" AND the conversation contains "Structural evaluation (first principles)":
- Read the BEAMS section of the evaluation to find which beam IDs failed and what check failed (BEND, SHEAR, DEFL_TL, DEFL_LL)
- Read the COLUMNS section to find which column IDs failed
- Set action="final" and write specific options using ONLY those exact element IDs from the evaluation
- Do NOT use the what-if span-extension format above — that is only for column removal simulations

For DEFLECTION failures (DEFL_TL or DEFL_LL): propose (1) adding a midspan column between the beam's endpoint columns to halve the span, (2) upgrading to the next IPE/RCC/Timber section tier, (3) reducing the tributary width by adding a parallel beam.
For BENDING failures (BEND): propose (1) upgrading to the next section tier, (2) adding a column at the midspan location.
For SHEAR failures (SHEAR): propose (1) increasing section width, (2) adding a column near the support.
For COLUMN stress/buckling failures: propose (1) upgrading column section, (2) reducing floor area tributary to that column.

Never guess element IDs. If a beam is named "CD_1" in the evaluation, use "CD_1" exactly.

GENERAL QUESTIONS (what rooms exist, what conflicts exist, what is permanent):
Answer directly from the layout JSON. Set action="final". Do not call any tool.

MODIFICATIONS (add grid, move element, confirmed change):
Set action="tool" and include the appropriate tool call.

Toolbox:
{tool_catalog}

Return strictly valid JSON:
{{
  "action": "final" | "tool",
  "final_response": "...",
  "tool_calls": [{{"name": "<tool-name>", "arguments": {{...}}}}, ...]
}}

Rules: JSON only, no markdown, no prose outside final_response.
If action is final: tool_calls must be []. If action is tool: final_response must be "".
"""


def build_reason_node(llm):

    def reason_node(state):
        cycle = state.get("cycle", 0)
        print(f"\n{'='*50}")
        print(f"  NODE: REASON  (cycle {cycle})")
        print(f"{'='*50}")

        # Trim history to stay within token limit
        # Cap each message at 600 chars so tool results (full layout JSON) don't blow the context
        def _cap(msg: dict, limit: int = 600) -> dict:
            c = msg.get("content", "")
            return {**msg, "content": c[:limit] + " ...[trimmed]"} if len(c) > limit else msg

        messages = state["messages"]
        kept = (messages[:1] + messages[-3:]) if len(messages) > 4 else messages
        trimmed_messages = [_cap(m) for m in kept]

        result = None
        last_error = None

        for attempt in range(3):
            try:
                result = call_llm(llm, SYSTEM_PROMPT, trimmed_messages, state["tool_catalog"])
                break
            except RuntimeError as e:
                if "non-empty 'tool_calls'" in str(e):
                    result = {"action": "final", "final_response": ""}
                    break
                last_error = e
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    print(f"LLM call failed (attempt {attempt+1}/3), retrying in {wait}s... {e}")
                    time.sleep(wait)
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    print(f"LLM call failed (attempt {attempt+1}/3), retrying in {wait}s... {e}")
                    time.sleep(wait)

        if result is None:
            raise RuntimeError(f"LLM failed after 3 attempts: {last_error}")

        if result["action"] == "final":
            state["final_response"] = result["final_response"]
            state["pending_tool_calls"] = None
        else:
            state["pending_tool_calls"] = result["tool_calls"]
            state["final_response"] = None

        state["came_from"] = "reason"
        return state

    return reason_node