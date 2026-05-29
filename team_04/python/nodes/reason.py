from __future__ import annotations
from typing import Any
from _runtime.llm import call_llm


# =============================================================================
# nodes/reason.py -- LLM nodes for TerraPilot (hub-and-spoke architecture).
#
# Three LLM nodes:
#
#   build_central_reason_node   Hub -- reads full conversation state and
#                               decides ONE of 9 actions per cycle.
#
#   build_optimization_node     Repair -- reads constraint violations and
#                               picks ONE manipulation tool to apply.
#
#   build_reason_output_node    Report -- writes the final architectural
#                               narrative (ALIGN / RESIST / FRAME / AVOID).
#
# All nodes use the same _make_node factory which calls call_llm() and
# parses the JSON response into:
#   action="tool"   -> pending_tool_calls set, next_action set
#   action="final"  -> final_response set, summary appended to messages
# =============================================================================


# -- Shared output format -----------------------------------------------------

_OUTPUT_FORMAT = """\
--- OUTPUT FORMAT -------------------------------------------------------------------
Return ONLY valid JSON on ONE line. No prose, no markdown, no extra text.

  action="tool"   -> {"action": "tool", "next_action": "ACTION_NAME", "tool_calls": [{"name": "TOOL_NAME", "arguments": {...}}]}
  action="final"  -> {"action": "final", "next_action": "ACTION_NAME", "final_response": "TEXT"}

Rules:
  * action="tool"   -- you want to call one or more tools NOW.
  * action="final"  -- no tools needed; provide content in final_response.
  * next_action must always be set to one of: suggest | generate_shape | evaluate |
    ask_user | check_constraints | optimize | explain | visualize | accept
  * For "generate_shape": action="tool", tool_calls=[...], next_action="generate_shape"
  * For "optimize": action="tool", tool_calls=[...], next_action="optimize"
  * For terminal actions (explain, accept, visualize): action="final", final_response="..."
  * For non-terminal non-tool actions (suggest, check_constraints, evaluate,
    ask_user): action="final", final_response="" (empty -- the worker node handles it)
-------------------------------------------------------------------------------------
"""


# =============================================================================
# CENTRAL REASON NODE
# =============================================================================

CENTRAL_REASON_PROMPT = """\
You are TerraPilot, an AI architectural design agent. You are the CENTRAL REASON NODE.
You are the hub. You read the full conversation history to understand what has been done,
then choose EXACTLY ONE action to perform next.

=== AVAILABLE ACTIONS ===

  suggest          Present design alternatives or explain options. Use when the user
                   asks for options or when a creative decision point is reached.

  generate_shape   Call site-reading and shape-creation tools to build or re-generate
                   the parametric form. Use this FIRST if no geometry_id exists yet.
                   Include tool_calls in your response.

  check_constraints Run all 5 constraint validators (auto). Use after generating a shape
                   or after a modification to verify compliance.

  optimize         Apply ONE manipulation tool to fix violations. Use when constraint
                   check found violations AND modification_iters < {max_mod_iters}.
                   Include tool_calls in your response.

  evaluate         Run all 3 evaluation tools to score the current design. Use when
                   constraints are clear (no violations or max iters reached).

  ask_user         Request clarification or approval from the user. Use when the brief
                   is ambiguous or when the user has not confirmed a direction.

  explain          Write the final architectural report. Use when evaluation is done
                   and the design is ready to present.

  visualize        Generate a visual summary of the current design state. Use when the
                   user asks to see the design.

  accept           Accept the current design as final with no further explanation.
                   Use only when the user explicitly says to finalise.

=== DECISION RULES ===

  1. No geometry_id exists             -> generate_shape
  2. geometry_id exists, not checked   -> check_constraints
  3. Violations + iters < {max_mod_iters}  -> optimize  (fix ONE violation per cycle)
  4. Violations + iters >= {max_mod_iters} -> evaluate  (forced -- stop looping)
  5. No violations, not evaluated       -> evaluate
  6. Evaluation done, no report yet     -> explain
  7. User asks for alternatives         -> suggest
  8. Unclear brief                      -> ask_user

=== TOOLS AVAILABLE FOR generate_shape ===

{shape_catalog}

=== TOOLS AVAILABLE FOR optimize ===

{manipulation_catalog}

{output_format}"""


# =============================================================================
# OPTIMIZATION NODE
# =============================================================================

OPTIMIZATION_PROMPT = """\
You are the OPTIMIZER. The constraint checker found violations.
Apply EXACTLY ONE manipulation tool to fix the most critical violation.

Read the most recent "=== CONSTRAINT CHECK RESULTS ===" message above for the
exact violations before deciding.

=== VIOLATION -> TOOL MAPPING (apply in priority order) ===

  fit   (footprint overlaps site boundary)
    -> scale_shape_tool_04  operation="scale_uniform"  scale_factor < 1.0
    OR scale_shape_tool_04  operation="offset_from_boundary"

  setback  (too close to a site edge)
    -> scale_shape_tool_04  operation="offset_from_boundary"
       offset_distance_m = required_setback - current_clearance + 0.5

  area  (GFA below requirement)
    -> stretch_arm_tool_04  extension_m = metres needed
    OR scale_shape_tool_04  operation="scale_uniform"  scale_factor > 1.0

  trees  (footprint conflicts with protected trees)
    -> bend_angle_tool_04   bend away from tree cluster
    OR courtyard_modifier_tool_04  carve void around trees

  access  (building too far from road / entrance)
    -> rotate_mirror_tool_04  operation="rotate"  angle = degrees to face road
    OR scale_shape_tool_04  operation="offset_from_boundary"

Use the geometry_id from the most recent "=== SHAPE STATE UPDATED ===" or
"=== MODIFIED SHAPE STATE UPDATED ===" message above.

Call ONE tool. Return action="tool", next_action="optimize", and put the
single tool call in tool_calls[].

=== TOOLS AVAILABLE ===

{manipulation_catalog}

{output_format}"""


# =============================================================================
# REASON OUTPUT NODE
# =============================================================================

REASON_OUTPUT_PROMPT = """\
You are the REPORT WRITER. All design cycles are complete.
Write the final architectural narrative. Do NOT call any tools.

Read the "=== EVALUATION RESULTS ===" and "=== SCORE STATE UPDATED ===" messages
above for scores. Read the "=== CONSTRAINT STATE UPDATED ===" messages for the
final violation status.

Write a report using this EXACT structure:

## Design Summary -- [Typology] / [Brief site description]

### ALIGN -- how the building responds to site forces
[Orientation relative to sun, wind, views, street access.  Be specific.]

### RESIST -- how violations were resolved
[List each correction made.  Be specific with tool and parameters used.]

### FRAME -- spatial qualities created
[What spatial experiences does the form produce?]

### AVOID -- what was protected
[Protected trees, noise, privacy setbacks, sight-lines.]

### Performance Metrics
  Spatial quality score  : [score]
  Performance score      : [score]
  Shape integrity score  : [score]

Return action="final", next_action="explain", final_response="<full report>".
Do NOT include tool_calls.

{output_format}"""


# =============================================================================
# Node builders
# =============================================================================

def _make_node(llm: Any, system_prompt: str, node_name: str) -> Any:
    """
    Generic LLM node factory.

    Parses LLM JSON output:
      action="tool"   -> sets pending_tool_calls + next_action
      action="final"  -> sets final_response + next_action; appends summary
    """

    def node(state: dict) -> dict:
        print(f"\n[{node_name}] calling LLM ...")
        messages = state.get("messages", [])
        result   = call_llm(llm, system_prompt, messages)
        action   = result.get("action", "final")
        nxt      = result.get("next_action") or result.get("action_name", "accept")

        if action == "tool":
            return {
                "pending_tool_calls": result.get("tool_calls", []),
                "next_action":        nxt,
            }
        else:
            summary_text = result.get("final_response", "")
            new_messages = list(messages) + [
                {"role": "assistant", "content": summary_text}
            ]
            return {
                "messages":           new_messages,
                "pending_tool_calls": None,
                "final_response":     summary_text if summary_text else state.get("final_response"),
                "next_action":        nxt,
            }

    return node


def build_central_reason_node(llm: Any, full_catalog: str, max_mod_iters: int) -> Any:
    """Hub node: reads full state from messages and decides next action."""
    # Split catalog into shape and manipulation sections for clarity
    shape_names = {
        "site_boundary_reader_04", "context_reader_04", "legal_constraints_reader_04",
        "shape_library_loader_04", "parametric_shape_generator_04",
    }
    manip_names = {
        "scale_shape_tool_04", "stretch_arm_tool_04", "width_modifier_tool_04",
        "courtyard_modifier_tool_04", "rotate_mirror_tool_04",
        "bend_angle_tool_04", "terrace_step_tool_04",
    }
    shape_lines = [l for l in full_catalog.splitlines() if any(n in l for n in shape_names)]
    manip_lines = [l for l in full_catalog.splitlines() if any(n in l for n in manip_names)]

    prompt = CENTRAL_REASON_PROMPT.format(
        max_mod_iters=max_mod_iters,
        shape_catalog="\n".join(shape_lines) or full_catalog,
        manipulation_catalog="\n".join(manip_lines) or full_catalog,
        output_format=_OUTPUT_FORMAT,
    )
    return _make_node(llm, prompt, "central_reason")


def build_optimization_node(llm: Any, manipulation_catalog: str) -> Any:
    """Optimizer node: picks ONE manipulation tool to fix the top violation."""
    prompt = OPTIMIZATION_PROMPT.format(
        manipulation_catalog=manipulation_catalog,
        output_format=_OUTPUT_FORMAT,
    )
    return _make_node(llm, prompt, "optimization")


def build_reason_output_node(llm: Any) -> Any:
    """Report writer node: produces ALIGN/RESIST/FRAME/AVOID narrative."""
    prompt = REASON_OUTPUT_PROMPT.format(output_format=_OUTPUT_FORMAT)
    return _make_node(llm, prompt, "reason_output")
