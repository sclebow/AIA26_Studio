from __future__ import annotations
import json
from typing import Any
from langgraph.graph import END, START, StateGraph
from nodes.reason import build_reason_node


# =============================================================================
# graph.py — Define the agent graph: state, nodes, and edges.
#
# This is the main file you edit to change how the agent works.
# - AgentState  : the data that flows through the graph
# - build_graph : wires nodes and edges together
# - run_agent   : called from main.py; builds and runs the graph once
# =============================================================================


# ---------------------------------------------------------------------------
# State — the data that every node can read and write.
# ---------------------------------------------------------------------------

class AgentState():
    messages: list[dict[str, Any]]       # full conversation history
    pending_tool_calls: list[dict[str, Any]] | None  # tool calls queued by the reason node
    final_response: str | None           # set when the agent is done
    iteration: int                       # current tool-call count
    max_iterations: int                  # safety cap to stop the process (set from .env)
    tool_catalog: str                    # formatted list of available MCP tools
    layout_json_string: str              # current layout as a JSON string, injected into tool calls


# ---------------------------------------------------------------------------
# Routing — decides which node runs next after "reason".
# ---------------------------------------------------------------------------

def _route(state: AgentState) -> str:
    if state["final_response"] is not None:
        return "finish"
    return "continue_reason"


def _loop(state: AgentState) -> AgentState:
    # Pass-through node used to avoid a direct self-edge on "reason".
    return state


# ---------------------------------------------------------------------------
# Graph wiring — add nodes and edges here.
# ---------------------------------------------------------------------------

def build_graph(ctx: Any) -> Any:
    # Create the state graph
    # Use the reason and tool nodes
    reason = build_reason_node(ctx.llm)

    # Initialize the graph
    graph = StateGraph(AgentState)

    # Add the nodes
    graph.add_node("reason", reason)
    graph.add_node("loop", _loop)

    # Add the edges
    graph.add_edge(START, "reason")
    graph.add_conditional_edges(
        "reason",
        _route,
        {
            "finish": END,
            "continue_reason": "loop",
        },
    )
    graph.add_edge("loop", "reason")

    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point — called from main.py.
# ---------------------------------------------------------------------------

def run_agent(prompt: str, ctx: Any) -> str:
    app = build_graph(ctx)

    initial_state = _build_initial_state(prompt, ctx)
    final_state = app.invoke(initial_state)

    # Uncomment these two lines to see the graph structure in the terminal
    print("\nWorkflow graph:")
    app.get_graph().print_ascii()

    final_response = final_state.get("final_response")
    if not isinstance(final_response, str):
        raise RuntimeError("Agent finished without a final response")
    return final_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_initial_state(prompt: str, ctx: Any) -> AgentState:

    # Convert the layout data to a JSON string
    layout_text = json.dumps(ctx.layout_data, indent=2)

    # Engineer the user message
    user_message = (
        "Context: the current layout is JSON below. "
        "Valid room names are rooms[].name.\n\n"
        f"User request:\n{prompt}\n\n"
        f"Current layout JSON:\n{layout_text}"
    )

    return {
        "messages": [{"role": "user", "content": user_message}],
        "pending_tool_calls": None,
        "final_response": None,
        "iteration": 0,
        "max_iterations": ctx.max_iterations,
        "tool_catalog": _format_tool_catalog(ctx.tools),
        "layout_json_string": json.dumps(ctx.layout_data),
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
