from __future__ import annotations
import logging
import json
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph
from nodes.preprocess import build_preprocess_node
from nodes.reason import build_reason_node
from nodes.search_node import build_search_node
from nodes.select import build_select_node
from nodes.adapt import build_adapt_node
from nodes.evaluate import build_evaluate_node
from nodes.feedback import build_feedback_node
from nodes.daylight import build_daylight_node


# =============================================================================
# graph.py — Define the agent graph: state, nodes, and edges.
#
# This is the main file you edit to change how the agent works.
# - AgentState  : the data that flows through the graph
# - build_graph : wires nodes and edges together
# - run_agent   : called from main.py; builds and runs the graph once
# =============================================================================

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State — the data that every node can read and write.
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    user_prompt: str                               # NEW - the raw use message prompt
    iteration: int                                 # current tool-call count
    final_response: str | None                     # set when the agent is done
    clarification: str | None                      # question for user clarification (set by all nodes except preprocess)
    feedback_history: list[str]                    # NEW - keep track of feedback given by the user
    graph_top_k: int                               # Candidate budget for graph search
    #-----------jsons for tools-----------
    layout_json_string: str                        # current layout as a JSON string, injected into tool calls 
    input_layout_json_string: str | None           # NEW - input layout, defining outline, as a JSON string, injected into tool calls 
    topology_graph_json_string: str | None         # Structured search payload extracted by reason
    search_results_json_string: str | None         # Search candidates
    layout_id: str | None         # Layout ID to be selected
    evaluation_json_string: str | None             # NEW - evaluation results
    #-----------results from nodes (for routing)-----------
    preprocess_result: str                         # Which node to go to after preprocess
    reason_result: str                             # Optional reason outcome label
    search_result: str                             # Result from search node: "select" | "failed"
    select_result: str                             # NEW - which node to go to after select: "success" | "failed"
    adapt_result: str | None                       # NEW - result from adapt node: "success" | "failed"
    daylight_result: str | None                    # Result from daylight node
    
    # REMOVED: messages, pending_tool_calls, tool_catalog
        
# ---------------------------------------------------------------------------
# Routing — decides which node runs next.
# ---------------------------------------------------------------------------
def _route_after_preprocessing(state: AgentState) -> str:
    result = state.get("preprocess_result")
    return {
        "reason": "reason",
        "select": "select",
        "end": "end",
    }.get(result, "end")
        
def _route_after_reason(state: AgentState) -> str:
    result = state.get("reason_result")
    return {
        "search_node": "search_node",
        "feedback": "feedback",
    }.get(result, "feedback")

def _route_after_search_node(state: AgentState) -> str:
    result = state.get("search_result")
    return {
        "select": "select",
    }.get(result, "feedback")
    
def _route_after_select(state: AgentState) -> str:
    result = state.get("select_result")
    return {
        "adapt": "adapt",      
        "daylight": "daylight"    
    }.get(result, "feedback")
    
def _route_after_adapt(state: AgentState) -> str:
    result = state.get("adapt_result")
    return {
        "daylight": "daylight",
    }.get(result, "feedback")

def _route_after_daylight(state: AgentState) -> str:
    result = state.get("daylight_result")
    return {
        "evaluate": "evaluate",
    }.get(result, "feedback")

# ---------------------------------------------------------------------------
# Graph wiring — add nodes and edges here.
# ---------------------------------------------------------------------------

def build_graph(ctx: Any) -> Any:
    """Build the layout agent graph."""
    reason = build_reason_node(ctx.llm)
    preprocess = build_preprocess_node()
    search_node = build_search_node()
    select = build_select_node()
    adapt = build_adapt_node(ctx.mcp_client)
    daylight = build_daylight_node(ctx.mcp_client)
    evaluate = build_evaluate_node(ctx.llm)
    feedback = build_feedback_node()
    
    # Wrap nodes to log entry/exit
    def make_logged_node(node_fn, node_name):
        def logged_wrapper(state):
            logger.info(f"▶️  Entering node: {node_name}")
            try:
                result = node_fn(state)
                logger.info(f"✅ {node_name} completed")
                return result
            except Exception as e:
                logger.error(f"❌ {node_name} failed: {str(e)}", exc_info=True)
                raise
        return logged_wrapper
    
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("reason", make_logged_node(reason, "reason"))
    workflow.add_node("preprocess", make_logged_node(preprocess, "preprocess"))
    workflow.add_node("search_node", make_logged_node(search_node, "search_node"))
    workflow.add_node("select", make_logged_node(select, "select"))
    workflow.add_node("adapt", make_logged_node(adapt, "adapt"))
    workflow.add_node("daylight", make_logged_node(daylight, "daylight"))
    workflow.add_node("evaluate", make_logged_node(evaluate, "evaluate"))
    workflow.add_node("feedback", make_logged_node(feedback, "feedback"))
    
    workflow.add_edge(START, "preprocess")
    
    # Add edges
    workflow.add_conditional_edges("preprocess", _route_after_preprocessing, {
        "reason": "reason",
        "select": "select",
        "end": END
    })
    workflow.add_conditional_edges("reason", _route_after_reason, {
        "search_node": "search_node",
        "feedback": "feedback"
    })
    workflow.add_conditional_edges("search_node", _route_after_search_node, {
        "select": "select",
        "feedback": "feedback"
    })
    workflow.add_conditional_edges("select", _route_after_select, {
        "adapt": "adapt",
        "daylight": "daylight",
         "feedback": "feedback"
    })
    workflow.add_conditional_edges("adapt", _route_after_adapt, {
        "daylight": "daylight",
        "select": "select"
    })
    workflow.add_conditional_edges("daylight", _route_after_daylight, {
        "evaluate": "evaluate",
        "feedback": "feedback"
    })
    workflow.add_edge("evaluate", "feedback")
    
    return workflow.compile()


# ---------------------------------------------------------------------------
# Entry point — called from main.py.
# ---------------------------------------------------------------------------

def run_agent(prompt: str, ctx: Any, session: dict | None = None) -> tuple[str, dict]:
    if session is None:
        session = {}
    
    logger.info(f"🚀 Analyzing your prompt...")
    
    app = build_graph(ctx)
    initial_state = _build_initial_state(prompt, ctx, session)
    final_state = app.invoke(initial_state)
    
    # Optional: log the entire graph at the end for debugging
    logger.info("\nWorkflow graph (Mermaid):")
    logger.info(app.get_graph().draw_mermaid())

    final_response = final_state.get("final_response")
    if final_response is None:
        logger.error(f"❌ Agent finished without final_response!")
        raise RuntimeError("Agent finished without setting final_response")
    
    logger.info(f"✅ Done")
    
    # Return response + updated session for next turn
    updated_session = {
    "layout_json_string": final_state.get("layout_json_string"),
    "layout_id": final_state.get("layout_id"),
    "topology_graph_json_string": final_state.get("topology_graph_json_string"),
    "feedback_history": final_state.get("feedback_history", []),
}
    
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
    if not layout_json:
        layout_json = json.dumps(getattr(ctx, "layout_data", {}), indent=2)

    input_layout_json = None
    if hasattr(ctx, 'input_layout_path') and ctx.input_layout_path:
        try:
            with open(ctx.input_layout_path, 'r') as f:
                input_layout_json = json.dumps(json.load(f))
        except:
            pass

    return {
        "user_prompt": prompt,
        "feedback_history": session.get("feedback_history", []),
        "clarification": session.get("clarification"),
        "iteration": 0,
        "final_response": None,
        "graph_top_k": 4,
        "layout_json_string": layout_json,
        "input_layout_json_string": input_layout_json,
        "topology_graph_json_string": session.get("topology_graph_json_string"),
        "search_results_json_string": None,
        "layout_id": session.get("layout_id"),
        "evaluation_json_string": None,
        "preprocess_result": None,
        "reason_result": None,
        "search_result": None,
        "select_result": None,
        "adapt_result": None,
        "daylight_result": None,
    }