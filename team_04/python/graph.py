from __future__ import annotations
import json
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph
from nodes.reason import build_reason_node
from nodes.tools import build_tool_node


# =============================================================================
# graph.py — TerraPilot agent graph.
#
# Workflow phases:
#   1. DESIGN  — site reading, shape generation, constraint checking, manipulation
#   2. EVALUATE — auto-runs 3 evaluators once geometry is ready
#   3. RESPOND  — LLM synthesises evaluation results into a final response
#
# Node map:
#   START → reason ──(tool call)──► tool ──────────────────► reason
#                  └──(final, geometry uneval)──► auto_evaluate ─► reason
#                  └──(final, evaluated)──────────────────────────► END
# =============================================================================

# ── Tool categories ───────────────────────────────────────────────────────────
_SHAPE_TOOLS = {"parametric_shape_generator_04", "shape_library_loader_04"}
_EVAL_TOOLS  = {"spatial_intention_evaluator_04", "performance_evaluator_04", "shape_integrity_evaluator_04"}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    messages:           list[dict[str, Any]]       # full conversation history
    pending_tool_calls: list[dict[str, Any]] | None # tool calls queued by reason
    final_response:     str | None                  # set when the agent is done
    iteration:          int                         # total tool-call count
    max_iterations:     int                         # safety cap
    tool_catalog:       str                         # formatted MCP tool list
    layout_json_string: str                         # injected into tool calls
    # ── TerraPilot workflow tracking ─────────────────────────────────────────
    phase:              str        # "design" | "evaluate" | "done"
    geometry_id:        str | None # active parametric geometry ID
    evaluation_done:    bool       # True after auto_evaluate has run


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route(state: AgentState) -> str:
    """Route after the reason node."""
    if state.get("final_response") is not None:
        # If a geometry exists but hasn't been evaluated yet → force evaluation
        if state.get("geometry_id") and not state.get("evaluation_done", False):
            return "evaluate"
        return "finish"
    if state.get("iteration", 0) >= state.get("max_iterations", 10):
        return "finish"
    return "run_tool"


# ---------------------------------------------------------------------------
# Auto-evaluate node
# ---------------------------------------------------------------------------

def _build_auto_evaluate_node(mcp_client: Any) -> Any:
    """Returns a node that auto-runs all 3 evaluators, then lets reason respond."""
    def auto_evaluate(state: AgentState) -> dict:
        geom_id = state.get("geometry_id")
        eval_parts: list[str] = []

        for tool_name in ["spatial_intention_evaluator_04",
                          "performance_evaluator_04",
                          "shape_integrity_evaluator_04"]:
            args = {"geometry_id": geom_id} if geom_id else {}
            try:
                result = mcp_client.call_tool(tool_name, args)
                eval_parts.append(f"[{tool_name}]:\n{result}")
            except Exception as exc:
                eval_parts.append(f"[{tool_name}]: ERROR — {exc}")

        messages = list(state.get("messages", []))
        messages.append({
            "role": "user",
            "content": (
                "Automatic evaluation complete. Results:\n\n"
                + "\n\n".join(eval_parts)
                + "\n\nNow synthesise these results into your final architectural assessment."
            ),
        })

        return {
            "messages":           messages,
            "evaluation_done":    True,
            "phase":              "evaluate",
            "final_response":     None,   # cleared so reason runs once more
            "pending_tool_calls": None,
        }

    return auto_evaluate


# ---------------------------------------------------------------------------
# Tracked tool node — standard tool execution + geometry_id extraction
# ---------------------------------------------------------------------------

def _build_tracked_tool_node(ctx: Any) -> Any:
    inner = build_tool_node(ctx.mcp_client, ctx.tools, ctx.edited_layout_path)

    def tracked_tool(state: AgentState) -> dict:
        pending    = state.get("pending_tool_calls") or []
        tool_names = [c.get("name", "") for c in pending]

        result = inner(state)   # mutates + returns state

        # Extract geometry_id when a shape tool succeeds
        if any(t in _SHAPE_TOOLS for t in tool_names):
            for msg in reversed(result.get("messages", [])):
                if msg.get("role") == "user" and msg.get("content", "").startswith("Tool result:"):
                    try:
                        payload = json.loads(msg["content"].removeprefix("Tool result:").strip())
                        gid = payload.get("data", {}).get("geometry_id")
                        if gid:
                            result["geometry_id"] = gid
                    except Exception:
                        pass
                    break

        return result

    return tracked_tool


# ---------------------------------------------------------------------------
# Graph wiring
# ---------------------------------------------------------------------------

def build_graph(ctx: Any) -> Any:
    reason       = build_reason_node(ctx.llm)
    tool         = _build_tracked_tool_node(ctx)
    auto_evaluate = _build_auto_evaluate_node(ctx.mcp_client)

    graph = StateGraph(AgentState)
    graph.add_node("reason",       reason)
    graph.add_node("tool",         tool)
    graph.add_node("auto_evaluate", auto_evaluate)

    graph.add_edge(START, "reason")
    graph.add_conditional_edges(
        "reason", _route,
        {"run_tool": "tool", "evaluate": "auto_evaluate", "finish": END},
    )
    graph.add_edge("tool",          "reason")
    graph.add_edge("auto_evaluate", "reason")

    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point — called from main.py.
# ---------------------------------------------------------------------------

def run_agent(prompt: str, ctx: Any) -> str:
    app = build_graph(ctx)

    initial_state = _build_initial_state(prompt, ctx)
    final_state = app.invoke(initial_state)

    # Print graph structure if grandalf is available
    try:
        print("\nWorkflow graph:")
        app.get_graph().print_ascii()
    except ImportError:
        pass

    final_response = final_state.get("final_response")
    if not isinstance(final_response, str):
        raise RuntimeError("Agent finished without a final response")
    return final_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_initial_state(prompt: str, ctx: Any) -> AgentState:
    return {
        "messages":           [{"role": "user", "content": prompt}],
        "pending_tool_calls": None,
        "final_response":     None,
        "iteration":          0,
        "max_iterations":     ctx.max_iterations,
        "tool_catalog":       _format_tool_catalog(ctx.tools),
        "layout_json_string": json.dumps(ctx.layout_data),
        # TerraPilot workflow
        "phase":              "design",
        "geometry_id":        None,
        "evaluation_done":    False,
    }

# Helper funtion to prepare the tool catalog for the LLM
def _format_tool_catalog(tools: list[dict[str, Any]]) -> str:
    lines = []
    for tool in tools:
        name = tool.get("name", "<unknown>")
        description = tool.get("description", "")
        schema = json.dumps(tool.get("inputSchema", {}))
        lines.append(f"- {name}: {description} | inputSchema={schema}")
    return "\n".join(lines)
