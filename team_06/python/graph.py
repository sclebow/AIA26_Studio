from __future__ import annotations
import logging
import json
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph
from nodes.preprocess import build_preprocessing_node
from nodes.brief import build_brief_node
from nodes.search import build_search_node
from nodes.choice import build_choice_node
from nodes.adapt import build_adapt_node
from nodes.evaluate import build_evaluate_node
from nodes.feedback import build_feedback_node
from nodes.boundary import build_boundary_node


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

class AgentState(TypedDict, total=False):
    user_prompt: str                               # NEW - the raw use message prompt
    topology_graph_json_string: str | None         # NEW - topology graph for search, as a JSON string
    layout_json_string: str                        # current layout as a JSON string, injected into tool calls 
    input_layout_json_string: str | None           # NEW - input layout, defining outline, as a JSON string, injected into tool calls 
    evaluation_json_string: str | None             # NEW - evaluation results
    search_results_json_string: str | None         # NEW - {id, score, description} only
    preprocessing_result: str                      # NEW - "evaluate" | "parse"
    feedback_result: str | None                    # NEW - "change_layout" | "change_boundary" | "success"
    iteration: int                                 # current tool-call count
    max_iterations: int                            # safety cap to stop the process (set from .env)
    final_response: str | None                     # set when the agent is done
    # REMOVED: messages, pending_tool_calls, tool_catalog

# ---------------------------------------------------------------------------
# Logging — helper to show what changed in state after each node runs.
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def _log_state_changes(node_name: str, state_before: dict, state_after: dict) -> None:
    """Log what changed in state after node execution."""
    changes = {}
    for key in state_after:
        if state_before.get(key) != state_after.get(key):
            old_val = state_before.get(key)
            new_val = state_after.get(key)
            # Shorten JSON strings for readability
            if isinstance(new_val, str) and len(new_val) > 100:
                new_val = new_val[:100] + "..."
            changes[key] = f"{old_val} → {new_val}"
    
    if changes:
        logger.info(f"  📝 State changes: {changes}")
        
# ---------------------------------------------------------------------------
# Routing — decides which node runs next.
# ---------------------------------------------------------------------------
def _route_after_preprocessing(state: AgentState) -> str:
    result = state.get("preprocessing_result")
    return {
        "research": "search",
        "modify_boundary": "boundary",
        "select_layout": "choice",
        "evaluate": "evaluate",
        "parse": "brief",
        "end": "end",
    }.get(result, "end")

def _route_after_brief(state: AgentState) -> str:
    # If brief asked a clarification question, stop here and return to user
    if state.get("final_response"):
        return "end"
    # Otherwise, proceed to search
    return "search"

def _route_after_search(state: AgentState) -> str:
    search_json = state.get("search_results_json_string", "[]")
    try:
        results = json.loads(search_json)
    except:
        results = []
    
    if len(results) == 0:
        return "end"
    else:
        return "choice"
    
def _route_after_choice(state: dict) -> str:
    # If choice returned a question (final_response), show it to user
    if state.get("final_response"):
        return "end"
    # Otherwise choice loaded a layout, proceed to adapt
    else:
        return "adapt"

def _route_after_adapt(state: AgentState) -> str:
    if state.get("final_response"):
        return "end"  
    return "evaluate"


def _route_after_feedback(state: AgentState) -> str:
    action = state.get("feedback_result")
    if action == "change_layout":
        return "search"
    elif action == "change_boundary":
        return "boundary"
    elif action == "success":
        state["final_response"] = "Layout successfully finalized."
        return "end"
    else:
        return "end"


def _route_after_boundary(state: AgentState) -> str:
    if state.get("final_response"):
        return "end"
    return "adapt"


# ---------------------------------------------------------------------------
# Graph wiring — add nodes and edges here.
# ---------------------------------------------------------------------------

def build_graph(ctx: Any) -> Any:
    """Build the layout agent graph."""
    brief = build_brief_node(ctx.llm)
    preprocessing = build_preprocessing_node()
    search = build_search_node()
    choice = build_choice_node(ctx.llm)
    adapt = build_adapt_node(ctx.mcp_client)
    evaluate = build_evaluate_node(ctx.mcp_client)
    feedback = build_feedback_node(ctx.llm)
    boundary = build_boundary_node(ctx.mcp_client)
    
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
    workflow.add_node("brief", make_logged_node(brief, "brief"))
    workflow.add_node("preprocessing", make_logged_node(preprocessing, "preprocessing"))
    workflow.add_node("search", make_logged_node(search, "search"))
    workflow.add_node("choice", make_logged_node(choice, "choice"))
    workflow.add_node("adapt", make_logged_node(adapt, "adapt"))
    workflow.add_node("evaluate", make_logged_node(evaluate, "evaluate"))
    workflow.add_node("feedback", make_logged_node(feedback, "feedback"))
    workflow.add_node("boundary", make_logged_node(boundary, "boundary"))
    
    workflow.add_edge(START, "preprocessing")
    
    # Add edges
    workflow.add_conditional_edges("preprocessing", _route_after_preprocessing, {
        "brief": "brief",
        "choice": "choice",
        "evaluate": "evaluate",
        "search": "search",
        "boundary": "boundary",
        "end": END
    })
    workflow.add_conditional_edges("brief", _route_after_brief, {
        "search": "search",
        "end": END
    })
    workflow.add_conditional_edges("search", _route_after_search, {
        "choice": "choice",
        "adapt": "adapt",
        "end": END
    })
    workflow.add_conditional_edges("adapt", _route_after_adapt, {
        "evaluate": "evaluate",
        "end": END
    })
    workflow.add_conditional_edges("choice", _route_after_choice, {
        "adapt": "adapt",
        "end": END
    })
    workflow.add_edge("evaluate", "feedback")
    workflow.add_conditional_edges("feedback", _route_after_feedback, {
        "search": "search",
        "boundary": "boundary",
        "end": END
    })
    workflow.add_conditional_edges("boundary", _route_after_boundary, {
    "adapt": "adapt",
    "end": END
    })
    
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
    #logger.info("\nWorkflow graph (Mermaid):")
    #logger.info(app.get_graph().draw_mermaid())

    final_response = final_state.get("final_response")
    if final_response is None:
        logger.error(f"❌ Agent finished without final_response!")
        raise RuntimeError("Agent finished without setting final_response")
    
    logger.info(f"✅ Done")
    
    # Return response + updated session for next turn
    updated_session = {
        "layout_json_string": final_state.get("layout_json_string"),
        "topology_graph_json_string": final_state.get("topology_graph_json_string"),
        "search_results_json_string": final_state.get("search_results_json_string"),
    }
    
    return final_response, updated_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_initial_state(prompt: str, ctx: Any, session: dict | None = None) -> AgentState:
    """Initialize state with priority: session → edited → reference → input layout."""
    if session is None:
        session = {}
    
    layout_json = session.get("layout_json_string")
    
    # If not in session, try loading from files
    if not layout_json:
        # Priority 1: edited_layout
        if hasattr(ctx, 'edited_layout_path') and ctx.edited_layout_path:
            try:
                with open(ctx.edited_layout_path, 'r') as f:
                    layout_json = json.dumps(json.load(f))
            except:
                pass
        
        # Priority 2: reference_layout
        if not layout_json and hasattr(ctx, 'reference_layout_path') and ctx.reference_layout_path:
            try:
                with open(ctx.reference_layout_path, 'r') as f:
                    layout_json = json.dumps(json.load(f))
            except:
                pass
        
        # Priority 3: input_layout
        if not layout_json and hasattr(ctx, 'input_layout_path') and ctx.input_layout_path:
            try:
                with open(ctx.input_layout_path, 'r') as f:
                    layout_json = json.dumps(json.load(f))
            except:
                pass
        
        # Fallback
        if not layout_json:
            layout_json = json.dumps(ctx.layout_data, indent=2)
    
    # Always load input_layout separately
    input_layout_json = None
    if hasattr(ctx, 'input_layout_path') and ctx.input_layout_path:
        try:
            with open(ctx.input_layout_path, 'r') as f:
                input_layout_json = json.dumps(json.load(f))
        except:
            pass
    
    return {
        "user_prompt": prompt,
        "layout_json_string": layout_json,
        "input_layout_json_string": input_layout_json,
        "evaluation_json_string": None,
        "search_results_json_string": session.get("search_results_json_string"),  # Carry over
        "preprocessing_result": None,
        "feedback_result": None,
        "topology_graph_json_string": session.get("topology_graph_json_string"),  # Carry over
        "iteration": 0,
        "max_iterations": ctx.max_iterations,
        "final_response": None,
    }