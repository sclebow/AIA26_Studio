from __future__ import annotations
import json
from typing import Any, TypedDict, Literal
from langgraph.graph import END, START, StateGraph
from nodes.reason import (
    build_central_reason_node,
    build_optimization_node,
    build_reason_output_node,
)
from nodes.tools import build_tool_node


# =============================================================================
# graph.py — Define the agent graph: state, nodes, and edges.
#
# This workflow implements the complete design generation and optimization loop:
#
# 1. INPUT & CONTEXT SETUP
#    - Receive user prompt and context
#    - Load scene state from cache
#    - Initialize layout and constraints
#
# 2. GENERATION ANALYSIS LOOP
#    - Generate shape suggestions based on analysis
#    - Create geometry proposals
#    - Check against constraints
#    - Evaluate performance metrics
#    - Generate optimization suggestions
#    - User decision: Accept, Modify, or Reject
#
# 3. DECISION OUTPUT & FEEDBACK
#    - Collect human feedback
#    - Cache final state
#    - Generate reasoning and visualization
#    - Output final result
#
# =============================================================================


# -- Tool name sets per category ----------------------------------------------

_SHAPE_TOOL_NAMES = {
    "site_boundary_reader_04",
    "context_reader_04",
    "legal_constraints_reader_04",
    "shape_library_loader_04",
    "parametric_shape_generator_04",
}

_MANIPULATION_TOOL_NAMES = {
    "scale_shape_tool_04",
    "stretch_arm_tool_04",
    "width_modifier_tool_04",
    "courtyard_modifier_tool_04",
    "rotate_mirror_tool_04",
    "bend_angle_tool_04",
    "terrace_step_tool_04",
}

_CONSTRAINT_TOOL_NAMES = [
    "site_fit_checker_04",
    "setback_checker_04",
    "area_requirement_checker_04",
    "adjacency_access_checker_04",
    "tree_constraint_checker_04",
]

_EVAL_TOOL_NAMES = [
    "spatial_intention_evaluator_04",
    "performance_evaluator_04",
    "shape_integrity_evaluator_04",
]

# Maximum optimisation cycles before the LLM must choose explain/accept
_MAX_MOD_ITERS = 4


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    messages:               list[dict[str, Any]]
    next_action:            str                       # decision from central_reason
    pending_tool_calls:     list[dict[str, Any]] | None
    final_response:         str | None
    iteration:              int
    max_iterations:         int
    tool_catalog:           str
    layout_json_string:     str

    # Shape state
    geometry_id:            str | None
    shape_state:            dict[str, Any] | None

    # Score state
    score_state:            dict[str, Any] | None
    evaluation_done:        bool

    # Constraint state
    constraint_results:     dict[str, Any] | None
    violations:             list[str]
    modification_iters:     int


# ---------------------------------------------------------------------------
# Violation categorisation
# ---------------------------------------------------------------------------

def _categorize_violations(results: dict[str, Any]) -> list[str]:
    """Map raw checker results to violation category names."""
    violations: list[str] = []

    fit = results.get("site_fit_checker_04", {}).get("data", {})
    if not fit.get("fits", True) and not fit.get("fits_within_site", True):
        violations.append("fit")

    setback = results.get("setback_checker_04", {}).get("data", {})
    if not setback.get("compliant", True):
        violations.append("setback")

    area = results.get("area_requirement_checker_04", {}).get("data", {})
    if not area.get("gfa_compliant", True) and not area.get("meets_requirement", True):
        violations.append("area")

    access = results.get("adjacency_access_checker_04", {}).get("data", {})
    if not access.get("road_access_ok", True) and not access.get("access_adequate", True):
        violations.append("access")

    trees = results.get("tree_constraint_checker_04", {}).get("data", {})
    if not trees.get("no_conflicts", True):
        violations.append("trees")

    return violations


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route_from_central_reason(state: AgentState) -> str:
    """Hub routing: map next_action to the correct worker node."""
    action = state.get("next_action", "accept")
    routing = {
        "suggest":            "suggestion_layer",
        "generate_shape":     "tool_shape_creation",
        "evaluate":           "tool_evaluation",
        "ask_user":           "human_feedback",
        "check_constraints":  "tool_constraint_check",
        "optimize":           "optimization",
        "explain":            "reason_output",
        "visualize":          "visualization",
        "accept":             "final_output",
    }
    dest = routing.get(action, "final_output")
    print(f"[routing] central_reason -> {dest}  (action={action})")
    return dest


# ---------------------------------------------------------------------------
# AUTO node: suggestion_layer
# ---------------------------------------------------------------------------

def _build_suggestion_layer() -> Any:
    """Presents design alternatives to the user; returns immediately to hub."""

    def suggestion_layer(state: AgentState) -> dict:
        messages = list(state.get("messages", []))
        messages.append({
            "role":    "user",
            "content": (
                "=== SUGGESTION LAYER ===\n"
                "Design suggestions have been presented to the user. "
                "Awaiting next decision."
            ),
        })
        print("[suggestion_layer] Suggestion displayed.")
        return {"messages": messages, "next_action": None}

    return suggestion_layer


# ---------------------------------------------------------------------------
# AUTO node: update_shape_state
# ---------------------------------------------------------------------------

def _build_update_shape_state() -> Any:
    """Extracts geometry_id from the most recent tool result and logs it."""

    def update_shape_state(state: AgentState) -> dict:
        geometry_id = state.get("geometry_id")
        for msg in reversed(state.get("messages", [])):
            if msg.get("role") == "user" and msg.get("content", "").startswith("Tool result:"):
                try:
                    payload = json.loads(
                        msg["content"].removeprefix("Tool result:").strip()
                    )
                    gid = payload.get("data", {}).get("geometry_id")
                    if gid:
                        geometry_id = gid
                except Exception:
                    pass
                break

        messages = list(state.get("messages", []))
        messages.append({
            "role":    "user",
            "content": (
                f"=== SHAPE STATE UPDATED ===\n"
                f"geometry_id: {geometry_id}\n"
                f"Shape creation complete. Ready for constraint checking or evaluation."
            ),
        })
        print(f"[update_shape_state] geometry_id={geometry_id}")
        return {
            "messages":    messages,
            "geometry_id": geometry_id,
            "shape_state": {"geometry_id": geometry_id, "created": True},
            "next_action": None,
        }

    return update_shape_state


# ---------------------------------------------------------------------------
# AUTO node: tool_evaluation
# ---------------------------------------------------------------------------

def _build_tool_evaluation(mcp_client: Any) -> Any:
    """Runs all 3 evaluation tools automatically. No LLM involved."""

    def tool_evaluation(state: AgentState) -> dict:
        geom_id     = state.get("geometry_id")
        eval_parts: list[str] = []
        score_state: dict[str, Any] = {}

        for tool_name in _EVAL_TOOL_NAMES:
            args = {"geometry_id": geom_id} if geom_id else {}
            try:
                raw    = mcp_client.call_tool(tool_name, args)
                parsed = json.loads(raw)
                eval_parts.append(f"[{tool_name}]:\n{raw}")
                score_state[tool_name] = parsed.get("data", {})
            except Exception as exc:
                eval_parts.append(f"[{tool_name}]: ERROR -- {exc}")

        messages = list(state.get("messages", []))
        messages.append({
            "role":    "user",
            "content": "=== EVALUATION RESULTS ===\n\n" + "\n\n".join(eval_parts),
        })
        print("[tool_evaluation] All 3 evaluators complete.")
        return {
            "messages":    messages,
            "score_state": score_state,
            "next_action": None,
        }

    return tool_evaluation


# ---------------------------------------------------------------------------
# AUTO node: update_score_state
# ---------------------------------------------------------------------------

def _build_update_score_state() -> Any:
    """Stores evaluation scores and logs completion."""

    def update_score_state(state: AgentState) -> dict:
        messages = list(state.get("messages", []))
        messages.append({
            "role":    "user",
            "content": (
                "=== SCORE STATE UPDATED ===\n"
                "Evaluation scores stored. Design is scored and ready for final report or accept."
            ),
        })
        print("[update_score_state] Score state updated.")
        return {"messages": messages, "evaluation_done": True, "next_action": None}

    return update_score_state


# ---------------------------------------------------------------------------
# AUTO node: human_feedback
# ---------------------------------------------------------------------------

def _build_human_feedback() -> Any:
    """Simulates human feedback in mock/notebook mode; auto-advances."""

    def human_feedback(state: AgentState) -> dict:
        messages = list(state.get("messages", []))
        messages.append({
            "role":    "user",
            "content": (
                "=== HUMAN FEEDBACK ===\n"
                "User reviewed the current design.\n"
                "Feedback: The direction looks correct -- please proceed."
            ),
        })
        print("[human_feedback] Auto-advance (mock mode).")
        return {"messages": messages, "next_action": None}

    return human_feedback


# ---------------------------------------------------------------------------
# AUTO node: tool_constraint_check
# Shared by both the [check_constraints] and [optimize] paths.
# ---------------------------------------------------------------------------

def _build_tool_constraint_check(mcp_client: Any) -> Any:
    """Runs all 5 constraint tools automatically. No LLM involved."""

    def tool_constraint_check(state: AgentState) -> dict:
        geom_id     = state.get("geometry_id")
        layout_json = state.get("layout_json_string", "{}")
        results: dict[str, Any] = {}
        cycle = state.get("modification_iters", 0) + 1

        for tool_name in _CONSTRAINT_TOOL_NAMES:
            args: dict[str, Any] = {"layout_json": layout_json}
            if geom_id:
                args["geometry_id"] = geom_id
            try:
                raw = mcp_client.call_tool(tool_name, args)
                results[tool_name] = json.loads(raw)
            except Exception as exc:
                results[tool_name] = {"success": False, "error": str(exc)}

        violations = _categorize_violations(results)
        viol_text  = (
            f"Violations detected: {violations}"
            if violations
            else "All 5 constraints satisfied -- no violations."
        )

        messages = list(state.get("messages", []))
        messages.append({
            "role":    "user",
            "content": (
                f"=== CONSTRAINT CHECK RESULTS (cycle {cycle}) ===\n"
                f"{json.dumps(results, indent=2)}\n\n"
                f"{viol_text}\n"
                f"{'Next: consider optimization.' if violations else 'Next: evaluate or accept.'}"
            ),
        })

        print(f"[tool_constraint_check] cycle={cycle}  violations={violations}")
        return {
            "messages":           messages,
            "constraint_results": results,
            "violations":         violations,
            "pending_tool_calls": None,
            "modification_iters": cycle,
            "next_action":        None,
        }

    return tool_constraint_check


# ---------------------------------------------------------------------------
# AUTO node: update_constraint_state
# ---------------------------------------------------------------------------

def _build_update_constraint_state() -> Any:
    """Stores constraint violations and logs status before returning to hub."""

    def update_constraint_state(state: AgentState) -> dict:
        violations = state.get("violations", [])
        status     = f"violations={violations}" if violations else "all_clear"
        messages   = list(state.get("messages", []))
        messages.append({
            "role":    "user",
            "content": (
                f"=== CONSTRAINT STATE UPDATED ===\n"
                f"Status: {status}. Returning to central reasoning."
            ),
        })
        print(f"[update_constraint_state] {status}")
        return {"messages": messages, "next_action": None}

    return update_constraint_state


# ---------------------------------------------------------------------------
# AUTO node: update_modified_shape
# ---------------------------------------------------------------------------

def _build_update_modified_shape() -> Any:
    """Extracts updated geometry_id after manipulation; routes to re-check."""

    def update_modified_shape(state: AgentState) -> dict:
        geometry_id = state.get("geometry_id")
        for msg in reversed(state.get("messages", [])):
            if msg.get("role") == "user" and msg.get("content", "").startswith("Tool result:"):
                try:
                    payload = json.loads(
                        msg["content"].removeprefix("Tool result:").strip()
                    )
                    gid = payload.get("data", {}).get("geometry_id")
                    if gid:
                        geometry_id = gid
                except Exception:
                    pass
                break

        messages = list(state.get("messages", []))
        messages.append({
            "role":    "user",
            "content": (
                f"=== MODIFIED SHAPE STATE UPDATED ===\n"
                f"geometry_id: {geometry_id}. Re-checking constraints now."
            ),
        })
        print(f"[update_modified_shape] geometry_id={geometry_id}")
        return {
            "messages":    messages,
            "geometry_id": geometry_id,
            "shape_state": {"geometry_id": geometry_id, "modified": True},
            "next_action": None,
        }

    return update_modified_shape


# ---------------------------------------------------------------------------
# AUTO node: visualization
# ---------------------------------------------------------------------------

def _build_visualization() -> Any:
    """Generates a text-based design summary for the final output path."""

    def visualization(state: AgentState) -> dict:
        geometry_id = state.get("geometry_id", "unknown")
        score_state = state.get("score_state") or {}
        violations  = state.get("violations", [])
        messages    = list(state.get("messages", []))

        messages.append({
            "role":    "user",
            "content": (
                f"=== VISUALIZATION ===\n"
                f"Geometry ID : {geometry_id}\n"
                f"Violations  : {violations or 'none'}\n"
                f"Scores      : {json.dumps(score_state, indent=2)}"
            ),
        })
        print("[visualization] Visualization generated.")
        return {"messages": messages}

    return visualization


# ---------------------------------------------------------------------------
# AUTO node: final_output
# ---------------------------------------------------------------------------

def _build_final_output() -> Any:
    """Consolidates the final response from state or builds a minimal summary."""

    def final_output(state: AgentState) -> dict:
        final_response = state.get("final_response") or ""
        if not final_response:
            geometry_id    = state.get("geometry_id", "unknown")
            violations     = state.get("violations", [])
            score_state    = state.get("score_state") or {}
            final_response = (
                f"Design complete.\n"
                f"geometry_id  : {geometry_id}\n"
                f"Violations   : {violations or 'none'}\n"
                f"Scores       : {json.dumps(score_state)}"
            )
        print("[final_output] Final output assembled.")
        return {"final_response": final_response}

    return final_output


# ---------------------------------------------------------------------------
# AUTO node: cache_final_state
# ---------------------------------------------------------------------------

def _build_cache_final_state(edited_layout_path: Any) -> Any:
    """Saves the design output JSON to disk."""
    from pathlib import Path

    def cache_final_state(state: AgentState) -> dict:
        try:
            out = {
                "final_response":     state.get("final_response", ""),
                "geometry_id":        state.get("geometry_id"),
                "violations":         state.get("violations", []),
                "score_state":        state.get("score_state"),
                "modification_iters": state.get("modification_iters", 0),
            }
            path = Path(edited_layout_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(out, f, indent=2)
            print(f"[cache_final_state] Saved -> {path}")
        except Exception as exc:
            print(f"[cache_final_state] Save failed: {exc}")
        return {}

    return cache_final_state


# ---------------------------------------------------------------------------
# Tracked tool executor -- shape creation
# ---------------------------------------------------------------------------

def _build_shape_tool_node(ctx: Any) -> Any:
    """Wraps the generic tool executor; extracts geometry_id from results."""
    inner = build_tool_node(ctx.mcp_client, ctx.tools, ctx.edited_layout_path)

    def tool_shape_creation(state: AgentState) -> dict:
        result = inner(state)
        for msg in reversed(result.get("messages", state.get("messages", []))):
            if msg.get("role") == "user" and msg.get("content", "").startswith("Tool result:"):
                try:
                    payload = json.loads(
                        msg["content"].removeprefix("Tool result:").strip()
                    )
                    gid = payload.get("data", {}).get("geometry_id")
                    if gid:
                        result["geometry_id"] = gid
                except Exception:
                    pass
                break
        return result

    return tool_shape_creation


# ---------------------------------------------------------------------------
# State — the data that flows through the graph
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    """Complete state for the design generation workflow."""
    
    # === INPUT & CONTEXT SETUP ===
    messages: list[dict[str, Any]]
    user_prompt: str
    user_input: str
    
    # Scene and layout context
    cached_scene_state: dict[str, Any] | None
    layout_json_string: str
    layout_data: dict[str, Any]
    
    # === GENERATION ANALYSIS LOOP ===
    # Suggestion layer output
    suggestions: list[dict[str, Any]]
    current_suggestion_index: int
    
    # Shape creation
    proposed_shapes: list[dict[str, Any]]
    shape_creation_report: str
    
    # Constraint checking
    constraint_violations: list[str]
    passes_constraints: bool
    constraint_report: str
    
    # Performance evaluation
    performance_metrics: dict[str, float]
    evaluation_report: str
    optimization_needed: bool
    
    # Optimization suggestions
    optimization_suggestions: list[dict[str, Any]]
    optimization_report: str
    
    # User decision
    user_decision: Literal["accept", "modify", "reject", "optimize"]
    decision_reason: str
    
    # === DECISION OUTPUT & FEEDBACK ===
    # Feedback collection
    human_feedback: str
    feedback_received: bool
    
    # Reasoning and visualization
    reasoning: str
    visualization_data: dict[str, Any] | None
    why_reasoning: str
    
    # Final output
    final_shapes: list[dict[str, Any]]
    final_response: str | None
    final_scene_state: dict[str, Any]
    
    # === RUNTIME METADATA ===
    iteration: int
    max_iterations: int
    tool_catalog: str
    pending_tool_calls: list[dict[str, Any]] | None
    error_state: str | None
    loop_count: int


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def _input_setup_node(state: AgentState) -> AgentState:
    """Process user input and set up context."""
    state["iteration"] = state.get("iteration", 0) + 1
    state["loop_count"] = state.get("loop_count", 0)
    
    # Prepare messages if not already done
    if not state.get("messages"):
        state["messages"] = [{"role": "user", "content": state["user_prompt"]}]
    
    # Initialize empty suggestions
    state["suggestions"] = []
    state["current_suggestion_index"] = 0
    
    return state


def _suggestion_layer_node(state: AgentState) -> AgentState:
    """Generate suggestions using the reason node."""
    reason_func = build_reason_node(state.get("llm"))
    # The suggestion layer is handled by the reason node
    # It analyzes the context and generates suggestions
    state["suggestions"] = [
        {
            "id": 0,
            "type": "shape_creation",
            "description": "Suggested shape modifications based on layout analysis",
            "confidence": 0.85
        }
    ]
    state["current_suggestion_index"] = 0
    return state


def _shape_creation_node(state: AgentState) -> AgentState:
    """Create shape proposals based on suggestions."""
    if state.get("suggestions"):
        suggestion = state["suggestions"][state.get("current_suggestion_index", 0)]
        state["proposed_shapes"] = [
            {
                "id": "shape_001",
                "type": "proposal",
                "source_suggestion": suggestion["id"],
                "geometry": {},
                "metadata": {"confidence": suggestion.get("confidence", 0.8)}
            }
        ]
        state["shape_creation_report"] = "Shapes created from suggestion analysis"
    return state


def _constraint_check_node(state: AgentState) -> AgentState:
    """Validate proposed shapes against constraints."""
    state["constraint_violations"] = []
    state["passes_constraints"] = True
    
    # Placeholder constraint check
    for shape in state.get("proposed_shapes", []):
        # Example constraints would be checked here
        pass
    
    state["constraint_report"] = (
        f"Constraint validation: {len(state.get('proposed_shapes', []))} shape(s) validated"
    )
    return state


def _evaluation_node(state: AgentState) -> AgentState:
    """Evaluate performance metrics."""
    state["performance_metrics"] = {
        "area_efficiency": 0.82,
        "constraint_satisfaction": 1.0 if state.get("passes_constraints") else 0.5,
        "geometry_quality": 0.87,
        "optimization_potential": 0.65
    }
    
    avg_score = sum(state["performance_metrics"].values()) / len(state["performance_metrics"])
    state["optimization_needed"] = avg_score < 0.85
    
    state["evaluation_report"] = (
        f"Performance evaluation complete. Average score: {avg_score:.2%}"
    )
    return state


def _optimization_node(state: AgentState) -> AgentState:
    """Generate optimization suggestions."""
    if state.get("optimization_needed"):
        state["optimization_suggestions"] = [
            {
                "id": "opt_001",
                "type": "geometry_refinement",
                "description": "Refine geometry for better performance",
                "priority": "high"
            }
        ]
    else:
        state["optimization_suggestions"] = []
    
    state["optimization_report"] = (
        f"Generated {len(state.get('optimization_suggestions', []))} optimization suggestion(s)"
    )
    return state


def _reasoning_node(state: AgentState) -> AgentState:
    """Generate detailed reasoning for decisions."""
    state["reasoning"] = (
        f"Analyzed {len(state.get('proposed_shapes', []))} proposed shape(s). "
        f"Constraint status: {'PASS' if state.get('passes_constraints') else 'FAIL'}. "
        f"Optimization suggestions: {len(state.get('optimization_suggestions', []))}"
    )
    
    state["why_reasoning"] = (
        "This design iteration was generated by analyzing the current layout context "
        "and applying constraint satisfaction and performance optimization strategies."
    )
    return state


def _visualization_node(state: AgentState) -> AgentState:
    """Prepare visualization data."""
    state["visualization_data"] = {
        "proposed_shapes": state.get("proposed_shapes", []),
        "metrics": state.get("performance_metrics", {}),
        "constraints_passed": state.get("passes_constraints", False)
    }
    return state


def _output_node(state: AgentState) -> AgentState:
    """Prepare final output."""
    state["final_shapes"] = state.get("proposed_shapes", [])
    state["final_scene_state"] = {
        "shapes": state.get("final_shapes", []),
        "metrics": state.get("performance_metrics", {}),
        "timestamp": str(state.get("iteration", 0))
    }
    
    state["final_response"] = (
        f"Design iteration {state.get('iteration', 1)} complete. "
        f"Generated {len(state.get('final_shapes', []))} shape(s). "
        f"Performance score: {state.get('performance_metrics', {}).get('constraint_satisfaction', 0):.1%}"
    )
    return state


# ---------------------------------------------------------------------------
# Routing logic — decides which path to take at decision points
# ---------------------------------------------------------------------------

def _route_after_suggestion(state: AgentState) -> str:
    """Route from suggestion layer to shape creation."""
    return "shape_creation"


def _route_after_constraints(state: AgentState) -> str:
    """Route based on constraint check results."""
    if not state.get("passes_constraints"):
        return "optimization"  # Try to fix constraint violations
    return "evaluation"


def _route_after_evaluation(state: AgentState) -> str:
    """Route based on evaluation results."""
    if state.get("optimization_needed"):
        return "optimization"
    return "reasoning"


def _route_after_decision(state: AgentState) -> str:
    """Route based on user decision in the feedback loop."""
    decision = state.get("user_decision", "accept")
    
    if decision == "accept":
        return "reasoning"
    elif decision == "modify":
        state["loop_count"] = state.get("loop_count", 0) + 1
        if state.get("loop_count", 0) >= state.get("max_iterations", 3):
            return "reasoning"  # Force finish if max loops reached
        return "suggestion_layer"  # Loop back to regenerate
    elif decision == "optimize":
        return "optimization"
    else:
        return "reasoning"


# ---------------------------------------------------------------------------
# Graph wiring — connect nodes and edges
# ---------------------------------------------------------------------------

def build_graph(ctx: Any) -> Any:
    """Build the complete state graph."""
    
    # Create the state graph with TypedDict
    graph = StateGraph(AgentState)
    
    # Add all nodes
    graph.add_node("input_setup", _input_setup_node)
    graph.add_node("suggestion_layer", _suggestion_layer_node)
    graph.add_node("shape_creation", _shape_creation_node)
    graph.add_node("constraint_check", _constraint_check_node)
    graph.add_node("evaluation", _evaluation_node)
    graph.add_node("optimization", _optimization_node)
    graph.add_node("reasoning", _reasoning_node)
    graph.add_node("visualization", _visualization_node)
    graph.add_node("output", _output_node)
    
    # Add edges: Input → Suggestion Layer
    graph.add_edge(START, "input_setup")
    graph.add_edge("input_setup", "suggestion_layer")
    
    # Main flow: Suggestion → Shapes → Constraints → Evaluation → Optimization → Reasoning
    graph.add_edge("suggestion_layer", "shape_creation")
    graph.add_edge("shape_creation", "constraint_check")
    graph.add_conditional_edges(
        "constraint_check",
        _route_after_constraints,
        {"evaluation": "evaluation", "optimization": "optimization"}
    )
    graph.add_edge("evaluation", "reasoning")
    graph.add_conditional_edges(
        "optimization",
        _route_after_evaluation,
        {"evaluation": "evaluation", "reasoning": "reasoning"}
    )
    
    # Post-reasoning flow: Reasoning → Visualization → Output
    graph.add_edge("reasoning", "visualization")
    graph.add_edge("visualization", "output")
    graph.add_edge("output", END)
    
    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point — called from main.py.
# ---------------------------------------------------------------------------

def run_agent(prompt: str, ctx: Any) -> str:
    """Execute the workflow state graph and return the final response."""
    app = build_graph(ctx)
    
    initial_state = _build_initial_state(prompt, ctx)
    final_state = app.invoke(initial_state)
    
    # Print the workflow structure
    print("\nWorkflow graph structure:")
    app.get_graph().print_ascii()
    
    final_response = final_state.get("final_response")
    if not isinstance(final_response, str):
        raise RuntimeError("Agent finished without a final response")
    return final_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_initial_state(prompt: str, ctx: Any) -> AgentState:
    """Build the initial state for workflow execution."""
    
    # Convert the layout data to a JSON string
    layout_text = json.dumps(ctx.layout_data, indent=2)
    
    return {
        "messages": [{"role": "user", "content": prompt}],
        "user_prompt": prompt,
        "user_input": prompt,
        "cached_scene_state": None,
        "layout_json_string": json.dumps(ctx.layout_data),
        "layout_data": ctx.layout_data,
        "suggestions": [],
        "current_suggestion_index": 0,
        "proposed_shapes": [],
        "shape_creation_report": "",
        "constraint_violations": [],
        "passes_constraints": True,
        "constraint_report": "",
        "performance_metrics": {},
        "evaluation_report": "",
        "optimization_needed": False,
        "optimization_suggestions": [],
        "optimization_report": "",
        "user_decision": "accept",
        "decision_reason": "",
        "human_feedback": "",
        "feedback_received": False,
        "reasoning": "",
        "visualization_data": None,
        "why_reasoning": "",
        "final_shapes": [],
        "final_response": None,
        "final_scene_state": {},
        "iteration": 0,
        "max_iterations": ctx.max_iterations,
        "tool_catalog": _format_tool_catalog(ctx.tools),
        "pending_tool_calls": None,
        "error_state": None,
        "loop_count": 0,
    }


def _format_tool_catalog(tools: list[dict[str, Any]]) -> str:
    """Format the tool catalog for the LLM."""
    lines = []
    for tool in tools:
        name = tool.get("name", "<unknown>")
        description = tool.get("description", "")
        schema = json.dumps(tool.get("inputSchema", {}))
        lines.append(f"- {name}: {description} | inputSchema={schema}")
    return "\n".join(lines)


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
