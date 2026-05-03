from __future__ import annotations
import json
from typing import Any
from langgraph.graph import END, START, StateGraph
from _runtime.llm import call_llm
from nodes.tools import build_tool_node


# =============================================================================
# graph.py — Agent graph implementing the cost-calculation & trade-off workflow.
#
# Graph structure follows flowchart_sketch.json:
#   user_prompt → reasoning (hub)
#     → clarify_with_user (if data missing) → reasoning
#     → extract_intend → trade_off_advice → extract_advice_intent
#                          → define_baseline/alternative_scenario
#                          → price_calculation_request
#                      → price_calculation_request (direct)
#     → extract_input_data → layout_processing ↔ tool
#                           → price_calculation_request
#   price_calculation_request → element_identification ↔ tool
#     → price_gathering_by_type ↔ tool
#     → construct_model → reasoning (if incomplete) | cost_calculation
#   cost_calculation → generate_heatmap ↔ tool → present_heatmap
#                                                   → modify_price_request → reasoning
#                                                   → END
#                   → calculate_delta → generate_recommendation → present_comparison
#                                                   → modify_price_request → reasoning
#                                                   → END
# =============================================================================


# ---------------------------------------------------------------------------
# State — the data that every node can read and write.
# ---------------------------------------------------------------------------

class AgentState():
    # Original fields
    messages: list[dict[str, Any]]
    pending_tool_calls: list[dict[str, Any]] | None
    final_response: str | None
    iteration: int
    max_iterations: int
    tool_catalog: str
    layout_json_string: str

    # Workflow tracking fields
    workflow_step: str            # last active step name (for post-tool routing)
    user_intent: str | None       # "trade_off_advice" | "price_calculation"
    clarification_needed: bool    # whether to stop and ask the user
    input_data_ready: bool        # layout/input data validated
    has_layout: bool              # layout JSON is present in state
    scenario_type: str | None     # "baseline" | "alternative"
    measurements_ready: bool      # element measurements have been gathered
    costs_ready: bool             # unit costs retrieved from database
    is_baseline_cost: bool | None # True = baseline pass, False = alternative pass
    heatmap_generated: bool       # heatmap tool has completed
    delta: float | None           # cost delta between scenarios
    recommendation: str | None    # generated trade-off recommendation text
    modification_requested: bool  # loop flag: continue to alternative or re-run
    model_complete: bool          # cost model has all required data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_intent(messages: list[dict]) -> str:
    """Keyword-based intent classification from conversation text."""
    text = " ".join(m.get("content", "") for m in messages).lower()
    trade_off_kws = [
        "compare", "trade-off", "tradeoff", "trade off", "alternative",
        "which is better", "baseline vs", "scenario", "versus", " vs ",
        "comparison", "better option",
    ]
    return "trade_off_advice" if any(kw in text for kw in trade_off_kws) else "price_calculation"


def _classify_scenario(messages: list[dict]) -> str:
    """Keyword-based scenario type classification from conversation text."""
    text = " ".join(m.get("content", "") for m in messages).lower()
    alt_kws = ["alternative", "modified", "new design", "what if", "instead", "option b", "variant"]
    return "alternative" if any(kw in text for kw in alt_kws) else "baseline"


# ---------------------------------------------------------------------------
# Routing functions — decide which node runs next after each step.
# ---------------------------------------------------------------------------

def _route_reasoning(state) -> str:
    if state.get("clarification_needed"):
        return "clarify_with_user"
    if not state.get("user_intent"):
        return "extract_intend"
    return "extract_input_data"


def _route_extract_intend(state) -> str:
    if state.get("user_intent") == "trade_off_advice":
        return "trade_off_advice"
    return "price_calculation_request"


def _route_extract_input_data(state) -> str:
    if state.get("clarification_needed"):
        return "clarify_with_user"
    if not state.get("has_layout"):
        return "layout_processing"
    return "price_calculation_request"


def _route_layout_processing(state) -> str:
    if state.get("pending_tool_calls"):
        return "tool"
    return "price_calculation_request"


def _route_extract_advice_intent(state) -> str:
    if state.get("scenario_type") == "alternative":
        return "define_alternative_scenario"
    return "define_baseline_scenario"


def _route_element_identification(state) -> str:
    if state.get("pending_tool_calls"):
        return "tool"
    return "price_gathering_by_type"


def _route_price_gathering(state) -> str:
    if state.get("pending_tool_calls"):
        return "tool"
    return "construct_model"


def _route_construct_model(state) -> str:
    if not state.get("model_complete", True):
        return "reasoning"
    return "cost_calculation"


def _route_cost_calculation(state) -> str:
    if state.get("is_baseline_cost") is False:
        return "calculate_delta"
    return "generate_heatmap"


def _route_generate_heatmap(state) -> str:
    if state.get("pending_tool_calls"):
        return "tool"
    return "present_heatmap"


def _route_present_heatmap(state) -> str:
    if state.get("modification_requested"):
        return "modify_price_request"
    return "finish"


def _route_present_comparison(state) -> str:
    if state.get("modification_requested"):
        return "modify_price_request"
    return "finish"


def _route_tool(state) -> str:
    """After a tool executes, return to the node that requested it."""
    return {
        "layout_processing":      "layout_processing",
        "element_identification": "element_identification",
        "price_gathering_by_type": "price_gathering_by_type",
        "generate_heatmap":       "generate_heatmap",
    }.get(state.get("workflow_step", ""), "reasoning")


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
1. Element types and their measurements (counts, areas, or volumes from tool results or layout JSON)
2. Unit costs for each element type (from the cost database tool results)

Rules:
- If the layout JSON and a tool result disagree on a count, trust the layout JSON.
- Minor discrepancies (e.g. tool returned 1 but layout shows 2) are NOT a reason to block — use the layout JSON value and proceed.
- Only respond DATA_MISSING if unit costs are completely absent.

If data is sufficient to calculate a cost, begin your final_response with MODEL_READY.
If unit cost data is truly missing, begin your final_response with DATA_MISSING.

Set action to "final".
"""


def _build_construct_model_node(llm):
    def node(state):
        print("\n[construct_model] Verifying cost model completeness...")
        attempts = state.get("construct_model_attempts", 0) + 1
        state["construct_model_attempts"] = attempts

        result = call_llm(llm, _CONSTRUCT_MODEL_PROMPT, state["messages"], state["tool_catalog"])
        resp = result.get("final_response", "MODEL_READY")
        incomplete = resp.upper().startswith("DATA_MISSING")

        if incomplete and attempts >= 2:
            print(f"  → forcing model complete after {attempts} attempts")
            incomplete = False

        state["model_complete"] = not incomplete
        if incomplete:
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
    tool                 = build_tool_node(ctx.mcp_client, ctx.tools, ctx.edited_layout_path, ctx.cost_db)

    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("reasoning",                 reasoning)
    graph.add_node("clarify_with_user",         clarify)
    graph.add_node("extract_intend",            extract_intend)
    graph.add_node("extract_input_data",        extract_input_data)
    graph.add_node("layout_processing",         layout_processing)
    graph.add_node("trade_off_advice",          trade_off_advice)
    graph.add_node("extract_advice_intent",     extract_advice_intent)
    graph.add_node("define_baseline_scenario",  define_baseline)
    graph.add_node("define_alternative_scenario", define_alternative)
    graph.add_node("price_calculation_request", price_calc_request)
    graph.add_node("element_identification",    element_id)
    graph.add_node("price_gathering_by_type",   price_gathering)
    graph.add_node("construct_model",           construct_model)
    graph.add_node("cost_calculation",          cost_calculation)
    graph.add_node("generate_heatmap",          generate_heatmap)
    graph.add_node("present_heatmap",           present_heatmap)
    graph.add_node("calculate_delta",           calculate_delta)
    graph.add_node("generate_recommendation",   gen_recommendation)
    graph.add_node("present_comparison",        present_comparison)
    graph.add_node("modify_price_request",      modify_request)
    graph.add_node("tool",                      tool)

    # ── Entry point ────────────────────────────────────────────────────────────
    graph.add_edge(START, "reasoning")

    # ── Reasoning hub (central router) ────────────────────────────────────────
    graph.add_conditional_edges("reasoning", _route_reasoning, {
        "clarify_with_user":  "clarify_with_user",
        "extract_intend":     "extract_intend",
        "extract_input_data": "extract_input_data",
    })

    # ── Clarification terminal ─────────────────────────────────────────────────
    graph.add_edge("clarify_with_user", END)

    # ── Intent extraction path ─────────────────────────────────────────────────
    graph.add_conditional_edges("extract_intend", _route_extract_intend, {
        "trade_off_advice":         "trade_off_advice",
        "price_calculation_request": "price_calculation_request",
    })

    # ── Input data validation path ─────────────────────────────────────────────
    graph.add_conditional_edges("extract_input_data", _route_extract_input_data, {
        "clarify_with_user":         "clarify_with_user",
        "layout_processing":         "layout_processing",
        "price_calculation_request": "price_calculation_request",
    })

    # ── Layout processing (bidirectional tool call) ────────────────────────────
    graph.add_conditional_edges("layout_processing", _route_layout_processing, {
        "tool":                      "tool",
        "price_calculation_request": "price_calculation_request",
    })

    # ── Trade-off advice path ──────────────────────────────────────────────────
    graph.add_edge("trade_off_advice",  "extract_advice_intent")
    graph.add_conditional_edges("extract_advice_intent", _route_extract_advice_intent, {
        "define_baseline_scenario":    "define_baseline_scenario",
        "define_alternative_scenario": "define_alternative_scenario",
    })
    graph.add_edge("define_baseline_scenario",    "price_calculation_request")
    graph.add_edge("define_alternative_scenario", "price_calculation_request")

    # ── Price calculation pipeline ─────────────────────────────────────────────
    graph.add_edge("price_calculation_request", "element_identification")

    graph.add_conditional_edges("element_identification", _route_element_identification, {
        "tool":                    "tool",
        "price_gathering_by_type": "price_gathering_by_type",
    })
    graph.add_conditional_edges("price_gathering_by_type", _route_price_gathering, {
        "tool":            "tool",
        "construct_model": "construct_model",
    })
    graph.add_conditional_edges("construct_model", _route_construct_model, {
        "reasoning":        "reasoning",
        "cost_calculation": "cost_calculation",
    })

    # ── Cost calculation branches ──────────────────────────────────────────────
    graph.add_conditional_edges("cost_calculation", _route_cost_calculation, {
        "generate_heatmap": "generate_heatmap",
        "calculate_delta":  "calculate_delta",
    })

    # ── Baseline path: heatmap + presentation ─────────────────────────────────
    graph.add_conditional_edges("generate_heatmap", _route_generate_heatmap, {
        "tool":           "tool",
        "present_heatmap": "present_heatmap",
    })
    graph.add_conditional_edges("present_heatmap", _route_present_heatmap, {
        "modify_price_request": "modify_price_request",
        "finish":               END,
    })

    # ── Alternative path: delta + recommendation + comparison ─────────────────
    graph.add_edge("calculate_delta",          "generate_recommendation")
    graph.add_edge("generate_recommendation",  "present_comparison")
    graph.add_conditional_edges("present_comparison", _route_present_comparison, {
        "modify_price_request": "modify_price_request",
        "finish":               END,
    })

    # ── Modification loop back to reasoning hub ────────────────────────────────
    graph.add_edge("modify_price_request", "reasoning")

    # ── Tool return routing ────────────────────────────────────────────────────
    graph.add_conditional_edges("tool", _route_tool, {
        "reasoning":               "reasoning",
        "layout_processing":       "layout_processing",
        "element_identification":  "element_identification",
        "price_gathering_by_type": "price_gathering_by_type",
        "generate_heatmap":        "generate_heatmap",
    })

    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point — called from main.py.
# ---------------------------------------------------------------------------

def run_agent(prompt: str, ctx: Any) -> str:
    app = build_graph(ctx)

    initial_state = _build_initial_state(prompt, ctx)
    final_state = app.invoke(initial_state)

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
    layout_text = json.dumps(ctx.layout_data, indent=2)

    user_message = (
        "Context: the current layout is the JSON below. "
        "Valid room names are rooms[].name.\n\n"
        f"User request:\n{prompt}\n\n"
        f"Current layout JSON:\n{layout_text}"
    )

    return {
        # Original fields
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
        "construct_model_attempts": 0,
    }


def _format_tool_catalog(tools: list[dict[str, Any]]) -> str:
    lines = []
    for tool in tools:
        name = tool.get("name", "<unknown>")
        description = tool.get("description", "")
        schema = json.dumps(tool.get("inputSchema", {}))
        lines.append(f"- {name}: {description} | inputSchema={schema}")
    return "\n".join(lines)
