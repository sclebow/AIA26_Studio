from __future__ import annotations
import json
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph
from nodes.reason import build_reason_node
from nodes.tools import build_tool_node


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
    return "run_tool"


# ---------------------------------------------------------------------------
# Node builders — each returns a node function ready for StateGraph.
# ---------------------------------------------------------------------------

# ── reasoning (central hub) ───────────────────────────────────────────────────

def _build_reasoning_node():
    def node(state):
        print("\n[reasoning] Evaluating workflow state...")
        state["has_layout"] = bool(state.get("layout_json_string"))
        state["clarification_needed"] = not state["has_layout"]
        state["modification_requested"] = False
        state["workflow_step"] = "reasoning"
        return state
    return node


# ── clarify_with_user ─────────────────────────────────────────────────────────

_CLARIFY_PROMPT = """You are a clarification assistant for a building cost-calculation agent.

The user's request cannot proceed because required information is missing.
Ask a concise, specific question to obtain what is needed (e.g. which layout to use,
which elements to cost, whether they want a comparison or a single calculation).

Set action to "final" and put your clarifying question in final_response.
"""


def _build_clarify_node(llm):
    def node(state):
        print("\n[clarify_with_user] Asking user for missing information...")
        result = call_llm(llm, _CLARIFY_PROMPT, state["messages"], state["tool_catalog"])
        state["final_response"] = result.get("final_response", "Could you provide more details about your request?")
        return state
    return node


# ── extract_intend ────────────────────────────────────────────────────────────

def _build_extract_intend_node():
    def node(state):
        print("\n[extract_intend] Classifying user intent...")
        state["user_intent"] = _classify_intent(state["messages"])
        state["workflow_step"] = "extract_intend"
        print(f"  → intent: {state['user_intent']}")
        return state
    return node


# ── extract_input_data ────────────────────────────────────────────────────────

def _build_extract_input_data_node():
    def node(state):
        print("\n[extract_input_data] Validating input data...")
        has_layout = bool(state.get("layout_json_string"))
        state["has_layout"] = has_layout
        state["input_data_ready"] = has_layout
        state["clarification_needed"] = not has_layout
        state["workflow_step"] = "extract_input_data"
        return state
    return node


# ── layout_processing ─────────────────────────────────────────────────────────

_LAYOUT_PROCESSING_PROMPT = """You need to retrieve the building layout JSON from the Grasshopper server.

Look for a tool that retrieves or reads the layout file and call it.
If no such tool exists or the layout is already loaded, set action to "final".

Available tools:
{tool_catalog}
"""


def _build_layout_processing_node(llm):
    def node(state):
        print("\n[layout_processing] Fetching layout data via tool...")
        state["workflow_step"] = "layout_processing"
        result = call_llm(llm, _LAYOUT_PROCESSING_PROMPT, state["messages"], state["tool_catalog"])
        if result["action"] == "tool":
            state["pending_tool_calls"] = result.get("tool_calls") or []
        else:
            state["has_layout"] = True
            state["pending_tool_calls"] = None
        return state
    return node


# ── trade_off_advice ──────────────────────────────────────────────────────────

def _build_trade_off_advice_node():
    def node(state):
        print("\n[trade_off_advice] Setting up trade-off analysis...")
        state["scenario_type"] = _classify_scenario(state["messages"])
        state["workflow_step"] = "trade_off_advice"
        return state
    return node


# ── extract_advice_intent ─────────────────────────────────────────────────────

def _build_extract_advice_intent_node():
    def node(state):
        print("\n[extract_advice_intent] Determining scenario type...")
        if not state.get("scenario_type"):
            state["scenario_type"] = _classify_scenario(state["messages"])
        state["workflow_step"] = "extract_advice_intent"
        print(f"  → scenario: {state['scenario_type']}")
        return state
    return node


# ── define_baseline_scenario / define_alternative_scenario ───────────────────

def _build_define_scenario_node(label: str):
    def node(state):
        print(f"\n[define_{label}_scenario] Configuring {label} scenario...")
        state["is_baseline_cost"] = (label == "baseline")
        state["workflow_step"] = f"define_{label}_scenario"
        return state
    return node


# ── price_calculation_request (merge) ─────────────────────────────────────────

def _build_price_calculation_request_node():
    def node(state):
        print("\n[price_calculation_request] Initiating cost calculation pipeline...")
        state["measurements_ready"] = False
        state["costs_ready"] = False
        state["model_complete"] = False
        state["workflow_step"] = "price_calculation_request"
        return state
    return node


# ── element_identification ────────────────────────────────────────────────────

_ELEMENT_ID_PROMPT = """You are identifying building elements and gathering their quantities.

Based on the layout JSON in the conversation, call the Grasshopper measurement tools:
- get_meters_by_type  → walls, beams, pipes, linear elements
- get_area_by_type    → floors, ceilings, roofs, facade panels
- get_volume_by_type  → concrete, fill, volumetric materials
- get_count_by_type   → doors, windows, fixtures, discrete items

Call all measurement tools relevant to the elements present.
If measurements are already in the conversation, set action to "final".

Available tools:
{tool_catalog}
"""


def _build_element_identification_node(llm):
    def node(state):
        print("\n[element_identification] Gathering element measurements...")
        state["workflow_step"] = "element_identification"
        result = call_llm(llm, _ELEMENT_ID_PROMPT, state["messages"], state["tool_catalog"])
        if result["action"] == "tool":
            state["pending_tool_calls"] = result.get("tool_calls") or []
            state["measurements_ready"] = False
        else:
            state["measurements_ready"] = True
            state["pending_tool_calls"] = None
        return state
    return node


# ── price_gathering_by_type ───────────────────────────────────────────────────

_PRICE_GATHERING_PROMPT = """You are retrieving unit costs for the identified building elements.

Element measurements are available in the conversation. Use the cost database tool
to look up the unit price for each element type.

If prices are already known from context, or no database tool is available,
set action to "final".

Available tools:
{tool_catalog}
"""


def _build_price_gathering_node(llm):
    def node(state):
        print("\n[price_gathering_by_type] Retrieving unit costs from database...")
        state["workflow_step"] = "price_gathering_by_type"
        result = call_llm(llm, _PRICE_GATHERING_PROMPT, state["messages"], state["tool_catalog"])
        if result["action"] == "tool":
            state["pending_tool_calls"] = result.get("tool_calls") or []
            state["costs_ready"] = False
        else:
            state["costs_ready"] = True
            state["pending_tool_calls"] = None
        return state
    return node


# ── construct_model ───────────────────────────────────────────────────────────

_CONSTRUCT_MODEL_PROMPT = """You are validating the completeness of the building cost model.

Review the conversation for:
1. Element types and their measurements (from tool results)
2. Unit costs for each element type

If all required data is present, begin your final_response with the word MODEL_READY.
If critical data is missing, begin your final_response with DATA_MISSING and briefly
describe what is absent.

Set action to "final".
"""


def _build_construct_model_node(llm):
    def node(state):
        print("\n[construct_model] Verifying cost model completeness...")
        result = call_llm(llm, _CONSTRUCT_MODEL_PROMPT, state["messages"], state["tool_catalog"])
        resp = result.get("final_response", "MODEL_READY")
        state["model_complete"] = not resp.upper().startswith("DATA_MISSING")
        if not state["model_complete"]:
            state["clarification_needed"] = True
            print(f"  → model incomplete: {resp}")
        else:
            print("  → model complete")
        state["workflow_step"] = "construct_model"
        return state
    return node


# ── cost_calculation ──────────────────────────────────────────────────────────

_COST_CALCULATION_PROMPT = """You are computing the total building cost from the cost model.

Using element measurements and unit costs from the conversation, calculate the total cost.
Show a concise breakdown by element type.

State explicitly whether this is the BASELINE or ALTERNATIVE cost calculation
based on the conversation context.

Set action to "final" with the cost summary in final_response.
"""


def _build_cost_calculation_node(llm):
    def node(state):
        print("\n[cost_calculation] Computing total cost...")
        result = call_llm(llm, _COST_CALCULATION_PROMPT, state["messages"], state["tool_catalog"])
        summary = result.get("final_response", "")
        state["messages"].append({"role": "assistant", "content": f"Cost calculation result:\n{summary}"})
        state["workflow_step"] = "cost_calculation"
        return state
    return node


# ── generate_heatmap ──────────────────────────────────────────────────────────

_GENERATE_HEATMAP_PROMPT = """You are generating a spatial cost heatmap for the building layout.

Use the heatmap generation tool to visualise the cost distribution across elements.
Pass the cost breakdown from the conversation to the tool.

If no heatmap tool is available, set action to "final".

Available tools:
{tool_catalog}
"""


def _build_generate_heatmap_node(llm):
    def node(state):
        print("\n[generate_heatmap] Creating cost heatmap...")
        state["workflow_step"] = "generate_heatmap"
        result = call_llm(llm, _GENERATE_HEATMAP_PROMPT, state["messages"], state["tool_catalog"])
        if result["action"] == "tool":
            state["pending_tool_calls"] = result.get("tool_calls") or []
            state["heatmap_generated"] = False
        else:
            state["heatmap_generated"] = True
            state["pending_tool_calls"] = None
        return state
    return node


# ── present_heatmap ───────────────────────────────────────────────────────────

_PRESENT_HEATMAP_PROMPT = """You are presenting the baseline cost heatmap results.

Summarise:
1. Total cost
2. Key observations about cost distribution across the layout
3. The highest-cost element types

Keep the summary clear and concise.

Set action to "final" with the summary in final_response.
"""


def _build_present_heatmap_node(llm):
    def node(state):
        print("\n[present_heatmap] Presenting baseline cost results...")
        result = call_llm(llm, _PRESENT_HEATMAP_PROMPT, state["messages"], state["tool_catalog"])
        summary = result.get("final_response", "Baseline cost heatmap generated.")

        # In trade-off flow after the baseline pass: store summary and loop for alternative
        if state.get("user_intent") == "trade_off_advice" and state.get("is_baseline_cost"):
            state["messages"].append({"role": "assistant", "content": f"Baseline heatmap summary:\n{summary}"})
            state["modification_requested"] = True
            state["final_response"] = None
        else:
            state["final_response"] = summary
            state["modification_requested"] = False

        state["workflow_step"] = "present_heatmap"
        return state
    return node


# ── calculate_delta ───────────────────────────────────────────────────────────

_CALCULATE_DELTA_PROMPT = """You are computing the cost difference between two building scenarios.

From the conversation, extract the baseline cost and the alternative cost, then calculate:
- Absolute delta (alternative cost minus baseline cost)
- Percentage change
- Which element types changed the most

Set action to "final" with the delta analysis in final_response.
"""


def _build_calculate_delta_node(llm):
    def node(state):
        print("\n[calculate_delta] Computing cost delta between scenarios...")
        result = call_llm(llm, _CALCULATE_DELTA_PROMPT, state["messages"], state["tool_catalog"])
        delta_text = result.get("final_response", "")
        state["messages"].append({"role": "assistant", "content": f"Delta analysis:\n{delta_text}"})
        state["workflow_step"] = "calculate_delta"
        return state
    return node


# ── generate_recommendation ───────────────────────────────────────────────────

_RECOMMENDATION_PROMPT = """You are generating a building design trade-off recommendation.

Based on the delta analysis in the conversation, provide:
1. Which scenario is more cost-effective and by how much
2. Any quality or functional considerations from the conversation
3. A clear, actionable recommendation

Set action to "final" with the recommendation in final_response.
"""


def _build_generate_recommendation_node(llm):
    def node(state):
        print("\n[generate_recommendation] Generating trade-off recommendation...")
        result = call_llm(llm, _RECOMMENDATION_PROMPT, state["messages"], state["tool_catalog"])
        rec = result.get("final_response", "")
        state["recommendation"] = rec
        state["messages"].append({"role": "assistant", "content": f"Recommendation:\n{rec}"})
        state["workflow_step"] = "generate_recommendation"
        return state
    return node


# ── present_comparison ────────────────────────────────────────────────────────

_PRESENT_COMPARISON_PROMPT = """You are presenting a full building cost trade-off comparison to the user.

Compile and present:
1. Baseline scenario — total cost
2. Alternative scenario — total cost
3. Cost delta (absolute and percentage)
4. Your recommendation (already in the conversation)
5. Offer to explore further modifications if the user wishes

Set action to "final" with the complete comparison in final_response.
"""


def _build_present_comparison_node(llm):
    def node(state):
        print("\n[present_comparison] Presenting cost comparison and recommendation...")
        result = call_llm(llm, _PRESENT_COMPARISON_PROMPT, state["messages"], state["tool_catalog"])
        state["final_response"] = result.get("final_response", "Here is the cost comparison.")
        state["modification_requested"] = False
        state["workflow_step"] = "present_comparison"
        return state
    return node


# ── modify_price_request (merge) ──────────────────────────────────────────────

def _build_modify_request_node():
    def node(state):
        print("\n[modify_price_request] Preparing for re-calculation...")
        # In trade-off flow: switch to the alternative scenario for the next pass
        if state.get("user_intent") == "trade_off_advice" and state.get("is_baseline_cost"):
            state["scenario_type"] = "alternative"
            state["is_baseline_cost"] = False
        # Reset computation fields so the pipeline runs fresh
        state["measurements_ready"] = False
        state["costs_ready"] = False
        state["model_complete"] = False
        state["heatmap_generated"] = False
        state["delta"] = None
        state["recommendation"] = None
        state["final_response"] = None
        state["pending_tool_calls"] = None
        state["workflow_step"] = "modify_price_request"
        return state
    return node


# ---------------------------------------------------------------------------
# Graph wiring
# ---------------------------------------------------------------------------

def build_graph(ctx: Any) -> Any:
    # Instantiate all node functions
    reasoning            = _build_reasoning_node()
    clarify              = _build_clarify_node(ctx.llm)
    extract_intend       = _build_extract_intend_node()
    extract_input_data   = _build_extract_input_data_node()
    layout_processing    = _build_layout_processing_node(ctx.llm)
    trade_off_advice     = _build_trade_off_advice_node()
    extract_advice_intent = _build_extract_advice_intent_node()
    define_baseline      = _build_define_scenario_node("baseline")
    define_alternative   = _build_define_scenario_node("alternative")
    price_calc_request   = _build_price_calculation_request_node()
    element_id           = _build_element_identification_node(ctx.llm)
    price_gathering      = _build_price_gathering_node(ctx.llm)
    construct_model      = _build_construct_model_node(ctx.llm)
    cost_calculation     = _build_cost_calculation_node(ctx.llm)
    generate_heatmap     = _build_generate_heatmap_node(ctx.llm)
    present_heatmap      = _build_present_heatmap_node(ctx.llm)
    calculate_delta      = _build_calculate_delta_node(ctx.llm)
    gen_recommendation   = _build_generate_recommendation_node(ctx.llm)
    present_comparison   = _build_present_comparison_node(ctx.llm)
    modify_request       = _build_modify_request_node()
    tool                 = build_tool_node(ctx.mcp_client, ctx.tools, ctx.edited_layout_path)

    graph = StateGraph(AgentState)

    # Add the nodes
    graph.add_node("reason", reason)
    graph.add_node("tool", tool)

    # Add the edges
    graph.add_edge(START, "reason")
    graph.add_conditional_edges("reason", _route, {"run_tool": "tool", "finish": END})
    graph.add_edge("tool", "reason")

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
        # Workflow tracking fields (all start unset/False/None)
        "workflow_step": "start",
        "user_intent": None,
        "clarification_needed": False,
        "input_data_ready": False,
        "has_layout": bool(ctx.layout_data),
        "scenario_type": None,
        "measurements_ready": False,
        "costs_ready": False,
        "is_baseline_cost": None,
        "heatmap_generated": False,
        "delta": None,
        "recommendation": None,
        "modification_requested": False,
        "model_complete": False,
    }


def _format_tool_catalog(tools: list[dict[str, Any]]) -> str:
    lines = []
    for tool in tools:
        name = tool.get("name", "<unknown>")
        description = tool.get("description", "")
        schema = json.dumps(tool.get("inputSchema", {}))
        lines.append(f"- {name}: {description} | inputSchema={schema}")
    return "\n".join(lines)
