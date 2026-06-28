from __future__ import annotations
import json
from typing import Any, Callable, TypedDict
from langgraph.graph import END, START, StateGraph
from nodes.preprocess import build_preprocess_node
from nodes.reason import build_reason_node
from nodes.search import build_search_node
from nodes.select import build_select_node
from nodes.adapt import build_adapt_node
from nodes.evaluate import build_evaluate_node
from nodes.feedback import build_feedback_node
from nodes.daylight import build_daylight_node
from nodes.routine import build_routine_node
from nodes.find_between import build_find_between_node


# =============================================================================
# graph.py — Define the agent graph: state, nodes, and edges.
#
# This is the main file you edit to change how the agent works.
# - AgentState  : the data that flows through the graph
# - build_graph : wires nodes and edges together
# - run_agent   : called from main.py; builds and runs the graph once
# =============================================================================

STATUS_MESSAGES = {
    "preprocess": "Reviewing request.",
    "reason": "Interpreting layout requirements.",
    "search": "Searching candidate layouts.",
    "find_between": "Finding layouts in between.",
    "select": "Loading the selected layout.",
    "adapt": "Adapting the layout to the provided boundary.",
    "daylight": "Running daylight analysis.",
    "evaluate": "Evaluating layout fit.",
    "routine": "Generating daily routine.",
    "feedback": "Preparing the response.",
}

# ---------------------------------------------------------------------------
# State — the data that every node can read and write.
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    user_prompt: str                               # NEW - the raw use message prompt
    forced_layout_id: str | None                   # Optional direct select request from the UI
    iteration: int                                 # current tool-call count
    final_response: str | None                     # set when the agent is done
    clarification: str | None                      # question for user clarification (set by all nodes except preprocess)
    needs_user_input: bool                         # explicit signal that the caller should collect another user turn
    status_messages: list[str]                     # progress updates for CLI/UI consumers
    feedback_history: list[str]                    # NEW - keep track of feedback given by the user
    graph_top_k: int                               # Candidate budget for graph search
    #-----------jsons for tools-----------
    layout_json_string: str                        # current layout as a JSON string, injected into tool calls 
    input_layout_json_string: str | None           # NEW - input layout, defining outline, as a JSON string, injected into tool calls 
    topology_graph_json_string: str | None         # Structured search payload extracted by reason
    search_results_json_string: str | None         # Search candidates
    embedding_map_json_string: str | None          # 2D coords for all layouts + query position
    layout_id: str | None         # Layout ID to be selected
    evaluation_json_string: str | None             # NEW - evaluation results
    routine_json_string: str | None                # Routine visualization payload
    routine_warning: str | None                    # Non-fatal error from routine node shown in UI
    adaptation_issues: list[str] | None           # Validation or tool issues collected during adaptation
    adaptation_failed: bool | None                # Whether adaptation failed and the graph fell back to the selected layout
    #-----------results from nodes (for routing)-----------
    preprocess_result: str                         # Which node to go to after preprocess
    reason_result: str                             # Optional reason outcome label
    search_result: str                             # Result from search node: "adapt" | "select" | "failed"
    select_result: str                             # NEW - which node to go to after select: "success" | "failed"
    adapt_result: str | None                       # NEW - result from adapt node: "success" | "failed"
    find_between_result: str | None                # Result from find_between node: "select" | "adapt" | "feedback"
    daylight_result: str | None                    # Result from daylight node
    daylight_issues: list[str] | None             # Daylight problems preserved for evaluation if analysis cannot run
    
    # REMOVED: messages, pending_tool_calls, tool_catalog
        
# ---------------------------------------------------------------------------
# Routing — decides which node runs next.
# ---------------------------------------------------------------------------
def _route_after_preprocessing(state: AgentState) -> str:
    result = state.get("preprocess_result")
    return {
        "reason": "reason",
        "select": "select",
        "find_between": "find_between",
        "end": "end",
    }.get(result, "end")

def _route_after_find_between(state: AgentState) -> str:
    result = state.get("find_between_result")
    return {
        "select": "select",
        "adapt": "adapt",
        "feedback": "feedback",
    }.get(result, "feedback")
        
def _route_after_reason(state: AgentState) -> str:
    result = state.get("reason_result")
    return {
        "search": "search",
        "evaluate": "evaluate",
        "feedback": "feedback",
    }.get(result, "feedback")

def _route_after_search(state: AgentState) -> str:
    result = state.get("search_result")
    return {
        "adapt": "adapt",
        "select": "select",
    }.get(result, "feedback")
    
def _route_after_select(state: AgentState) -> str:
    result = state.get("select_result")
    if result == "failed":
        return "feedback"
    if state.get("input_layout_json_string"):
        return "adapt"
    return {
        "adapt": "adapt",
        "daylight": "routine"
    }.get(result, "feedback")
    
def _route_after_adapt(state: AgentState) -> str:
    result = state.get("adapt_result")
    return {
        "daylight": "routine",
        "fallback_selected": "routine",
    }.get(result, "feedback")


# ---------------------------------------------------------------------------
# Graph wiring — add nodes and edges here.
# ---------------------------------------------------------------------------

def _session_from_state(state: AgentState) -> dict[str, Any]:
    return {
        "layout_json_string": state.get("layout_json_string"),
        "layout_id": state.get("layout_id"),
        "input_layout_json_string": state.get("input_layout_json_string"),
        "topology_graph_json_string": state.get("topology_graph_json_string"),
        "search_results_json_string": state.get("search_results_json_string"),
        "embedding_map_json_string": state.get("embedding_map_json_string"),
        "evaluation_json_string": state.get("evaluation_json_string"),
        "routine_json_string": state.get("routine_json_string"),
        "feedback_history": state.get("feedback_history", []),
        "needs_user_input": state.get("needs_user_input", False),
        "forced_layout_id": state.get("forced_layout_id"),
    }


def build_graph(ctx: Any, status_callback: Callable[[list[str], dict[str, Any] | None], None] | None = None) -> Any:
    """Build the layout agent graph."""
    status_updates: list[str] = []
    nodes_executed: list[str] = []
    reason = build_reason_node(ctx.llm)
    preprocess = build_preprocess_node()
    search = build_search_node()
    find_between = build_find_between_node()
    select = build_select_node()
    adapt = build_adapt_node(ctx.mcp_client)
    daylight = build_daylight_node(ctx.mcp_client)
    evaluate = build_evaluate_node(ctx.llm)
    feedback = build_feedback_node()
    routine = build_routine_node(ctx.llm)
    
    def make_instrumented_node(node_fn, node_name):
        def instrumented_wrapper(state):
            status_message = STATUS_MESSAGES.get(node_name, f"Running {node_name}.")
            status_updates.append(status_message)
            nodes_executed.append(node_name)
            print(f"Status: {status_message}", flush=True)
            result = node_fn(state)
            result["status_messages"] = list(status_updates)
            if status_callback is not None:
                merged_state = {**state, **result}
                status_callback(list(status_updates), _session_from_state(merged_state))
            return result
        return instrumented_wrapper
    
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("reason", make_instrumented_node(reason, "reason"))
    workflow.add_node("preprocess", make_instrumented_node(preprocess, "preprocess"))
    workflow.add_node("search", make_instrumented_node(search, "search"))
    workflow.add_node("find_between", make_instrumented_node(find_between, "find_between"))
    workflow.add_node("select", make_instrumented_node(select, "select"))
    workflow.add_node("adapt", make_instrumented_node(adapt, "adapt"))
    workflow.add_node("daylight", make_instrumented_node(daylight, "daylight"))
    workflow.add_node("evaluate", make_instrumented_node(evaluate, "evaluate"))
    workflow.add_node("routine", make_instrumented_node(routine, "routine"))
    workflow.add_node("feedback", make_instrumented_node(feedback, "feedback"))
    
    workflow.add_edge(START, "preprocess")
    
    # Add edges
    workflow.add_conditional_edges("preprocess", _route_after_preprocessing, {
        "reason": "reason",
        "select": "select",
        "find_between": "find_between",
        "end": END
    })
    workflow.add_conditional_edges("find_between", _route_after_find_between, {
        "select": "select",
        "adapt": "adapt",
        "feedback": "feedback",
    })
    workflow.add_conditional_edges("reason", _route_after_reason, {
        "search": "search",
        "evaluate": "evaluate",
        "feedback": "feedback"
    })
    workflow.add_conditional_edges("search", _route_after_search, {
        "adapt": "adapt",
        "select": "select",
        "feedback": "feedback"
    })
    workflow.add_conditional_edges("select", _route_after_select, {
        "adapt": "adapt",
        "routine": "routine",
        "feedback": "feedback"
    })
    workflow.add_conditional_edges("adapt", _route_after_adapt, {
        "routine": "routine",
        "feedback": "feedback"
    })
    workflow.add_edge("routine", "daylight")
    workflow.add_edge("daylight", "evaluate")
    workflow.add_edge("evaluate", "feedback")
    
    app = workflow.compile()
    app._status_updates = status_updates
    app._nodes_executed = nodes_executed
    return app


# ---------------------------------------------------------------------------
# Entry point — called from main.py.
# ---------------------------------------------------------------------------

def run_agent(
    prompt: str,
    ctx: Any,
    session: dict | None = None,
    status_callback: Callable[[list[str], dict[str, Any] | None], None] | None = None,
) -> tuple[str, dict]:
    if session is None:
        session = {}

    print("Status: Analyzing your request.", flush=True)
    
    app = build_graph(ctx, status_callback=status_callback)
    initial_state = _build_initial_state(prompt, ctx, session)
    final_state = app.invoke(initial_state)

    final_response = final_state.get("final_response")
    if final_response is None:
        raise RuntimeError("Agent finished without setting final_response")
    
    # Return response + updated session for next turn
    updated_session = _session_from_state(final_state)
    updated_session["status_messages"] = list(getattr(app, "_status_updates", []))
    updated_session["nodes_executed"] = list(getattr(app, "_nodes_executed", []))
    updated_session["routine_warning"] = final_state.get("routine_warning")

    return final_response, updated_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_initial_state(prompt: str, ctx: Any, session: dict | None = None) -> AgentState:
    if session is None:
        session = {}
    # Always ensure feedback_history is present
    if "feedback_history" not in session:
        session["feedback_history"] = []

    layout_json = session.get("layout_json_string")
    if layout_json is None and getattr(ctx, "layout_data", None):
        layout_json = json.dumps(ctx.layout_data)

    input_layout_json = session.get("input_layout_json_string")

    return {
        "user_prompt": prompt,
        "forced_layout_id": session.get("forced_layout_id"),
        "feedback_history": session.get("feedback_history", []),
        "clarification": session.get("clarification"),
        "needs_user_input": False,
        "status_messages": [],
        "iteration": 0,
        "final_response": None,
        "graph_top_k": 4,
        "layout_json_string": layout_json,
        "input_layout_json_string": input_layout_json,
        "topology_graph_json_string": session.get("topology_graph_json_string"),
        "search_results_json_string": session.get("search_results_json_string"),
        "embedding_map_json_string": session.get("embedding_map_json_string"),
        "layout_id": session.get("layout_id"),
        "evaluation_json_string": session.get("evaluation_json_string"),
        "routine_json_string": session.get("routine_json_string"),
        "routine_warning": None,
        "preprocess_result": None,
        "reason_result": None,
        "search_result": None,
        "select_result": None,
        "adapt_result": None,
        "find_between_result": None,
        "daylight_result": None,
    }