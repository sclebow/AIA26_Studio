from __future__ import annotations
import json
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph
from nodes.reason import build_reason_node
from nodes.tools import build_tool_node


# =============================================================================
# graph.py — Define the agent graph: state, nodes, and edges.
#
# This file is a LITERAL translation of the Mermaid flowchart.
# Each red/blue box from the diagram is its own node here.
# Each green box (tool) is dispatched through the tool node, which routes
# to the correct MCP tool (grasshopper, python, cost_db, heatmap).
# =============================================================================


# ---------------------------------------------------------------------------
# State — the data that every node can read and write.
# Expanded from the template to carry everything the flowchart needs.
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    # --- core (kept from template) ---
    messages: list[dict[str, Any]]            # full conversation history
    pending_tool_calls: list[dict[str, Any]] | None
    final_response: str | None
    iteration: int
    max_iterations: int
    tool_catalog: str
    layout_json_string: str

    # --- routing flags set by reasoning / extract* nodes ---
    needs_clarification: bool                 # reasoning -> clarifyUser
    task_known: bool                          # reasoning -> extractIntent
    input_data_known: bool                    # reasoning -> extractBudget / extractInputData
    intent: str | None                        # "trade_off_advice" | "price_calculation"
    advice_state: str | None                  # "baseline" | "alternative"

    # --- data extracted along the way ---
    budget: dict[str, Any] | None             # extracted budget info
    input_data: dict[str, Any] | None         # extracted input data
    has_layout: bool                          # is there a layout JSON?
    layout_data: dict[str, Any] | None        # layout JSON contents

    # --- price-calculation pipeline ---
    element_type_known: bool                  # priceCalcRequest -> elementIdentification
    needs_meters: bool
    needs_area: bool
    needs_volume: bool
    needs_count: bool
    quantities: dict[str, Any]                # filled by getMeters/getArea/getVolume/getCount
    prices: dict[str, Any] | None             # filled by priceGathering
    model: dict[str, Any] | None              # constructed cost model
    model_complete: bool                      # are element, type, quantity, price all known?
    cost: float | None                        # output of costCalculation

    # --- variance & comparison ---
    cost_kind: str | None                     # "baseline" | "alternative"
    baseline_cost: float | None
    alternative_cost: float | None
    delta: float | None
    has_budget_info: bool
    heatmap_generated: bool
    heatmap_path: str | None
    recommendation: str | None
    presented_comparison: bool
    modify_request: bool                      # user asked to modify after comparison


# =============================================================================
# Routing functions — one per decision point in the Mermaid diagram.
# Each returns the name of the next node (a key in the conditional_edges map).
# =============================================================================

def _route_reasoning(state: AgentState) -> str:
    # reasoning has 4 outgoing arrows in the diagram
    if state.get("final_response") is not None:
        return "finish"
    if state.get("pending_tool_calls"):
        return "tool"
    if state.get("needs_clarification"):
        return "clarify"
    if state.get("task_known"):
        return "extract_intent"
    if state.get("input_data_known"):
        # Two arrows leave to extractBudget AND extractInputData with the same
        # label. We pick extractInputData first; extractBudget is reached via
        # extractInputData branching when budget is part of the input.
        return "extract_input_data"
    return "extract_budget"


def _route_extract_intent(state: AgentState) -> str:
    if state.get("intent") == "trade_off_advice":
        return "trade_off_advice"
    return "price_calc_request"


def _route_extract_input_data(state: AgentState) -> str:
    # "Is there a layout?" -> layoutProcessing
    # "Input data and layout present" -> priceCalcRequest
    if state.get("has_layout") and state.get("input_data") is not None:
        return "price_calc_request"
    return "layout_processing"


def _route_extract_advice_intent(state: AgentState) -> str:
    if state.get("advice_state") == "alternative":
        return "define_alternative"
    return "define_baseline"


def _route_price_calc_request(state: AgentState) -> str:
    # "Is element & type known?" -> elementIdentification, else loop back to reasoning
    if state.get("element_type_known"):
        return "element_identification"
    return "reasoning"


def _route_element_identification(state: AgentState) -> str:
    # The diagram shows multiple parallel arrows. LangGraph conditional edges
    # pick ONE next node, so we order quantity gathering before priceGathering.
    # Each get* node loops back to elementIdentification until all needed
    # quantities are filled, then falls through to priceGathering.
    if state.get("needs_meters") and "meters" not in state.get("quantities", {}):
        return "get_meters"
    if state.get("needs_area") and "area" not in state.get("quantities", {}):
        return "get_area"
    if state.get("needs_volume") and "volume" not in state.get("quantities", {}):
        return "get_volume"
    if state.get("needs_count") and "count" not in state.get("quantities", {}):
        return "get_count"
    return "price_gathering"


def _route_construct_model(state: AgentState) -> str:
    if state.get("model_complete"):
        return "cost_calculation"
    return "reasoning"


def _route_budget_variance(state: AgentState) -> str:
    if state.get("cost_kind") == "baseline":
        return "generate_heatmap"
    return "calculate_delta"


def _route_generate_heatmap(state: AgentState) -> str:
    if state.get("heatmap_generated"):
        return "present_heatmap"
    # Heatmap not yet generated -> dispatch the heatmap tool
    return "tool"


def _route_present_heatmap(state: AgentState) -> str:
    # "No new question" -> finish
    return "finish"


def _route_calculate_delta(state: AgentState) -> str:
    if state.get("has_budget_info"):
        return "budget_aware_rec"
    return "generate_rec"


def _route_present_comparison(state: AgentState) -> str:
    if state.get("modify_request"):
        return "modify_price_request"
    return "finish"


# =============================================================================
# Logical node stubs — one per red/blue box in the Mermaid diagram.
#
# Each node takes the current state and returns a partial-state update dict.
# The actual logic (LLM calls, parsing, etc.) belongs inside these stubs;
# fill them in as you flesh out the agent.
# =============================================================================

def _make_reasoning_node(llm: Any) -> Any:
    base_reason = build_reason_node(llm)
    def node(state: AgentState) -> dict[str, Any]:
        # TODO: use the LLM to inspect the conversation and decide:
        #   - is clarification needed?  -> needs_clarification
        #   - is the task known?        -> task_known
        #   - are input data known?     -> input_data_known
        #   - is the agent done?        -> final_response
        return base_reason(state)
    return node


def _clarify_user_node(state: AgentState) -> dict[str, Any]:
    # TODO: ask the user for the missing info, then loop back to reasoning.
    return {"needs_clarification": False}


def _extract_intent_node(state: AgentState) -> dict[str, Any]:
    # TODO: parse the user's request and set intent to one of:
    #   "trade_off_advice" | "price_calculation"
    return {}


def _extract_budget_node(state: AgentState) -> dict[str, Any]:
    # TODO: pull budget figures (target, currency, etc.) from the prompt.
    return {}


def _extract_input_data_node(state: AgentState) -> dict[str, Any]:
    # TODO: pull layout reference, element list, etc., from the prompt.
    return {}


def _layout_processing_node(state: AgentState) -> dict[str, Any]:
    # Calls gettingLayoutJSON via the tool node (grasshopper).
    # TODO: queue the grasshopper call to fetch the layout.
    return {
        "pending_tool_calls": [
            {"tool": "grasshopper", "action": "get_layout_json", "args": {}}
        ]
    }


def _getting_layout_json_node(state: AgentState) -> dict[str, Any]:
    # Wrapper: enqueue the grasshopper tool call, results land in layout_data.
    return {
        "pending_tool_calls": [
            {"tool": "grasshopper", "action": "get_layout_json", "args": {}}
        ]
    }


def _trade_off_advice_node(state: AgentState) -> dict[str, Any]:
    # TODO: prepare the trade-off framing for the user.
    return {}


def _extract_advice_intent_node(state: AgentState) -> dict[str, Any]:
    # TODO: decide whether we are defining the baseline or an alternative.
    return {}


def _define_baseline_node(state: AgentState) -> dict[str, Any]:
    return {"cost_kind": "baseline"}


def _define_alternative_node(state: AgentState) -> dict[str, Any]:
    return {"cost_kind": "alternative"}


def _price_calc_request_node(state: AgentState) -> dict[str, Any]:
    # TODO: assemble what we know about elements/types for the calculation.
    return {}


def _element_identification_node(state: AgentState) -> dict[str, Any]:
    # TODO: for each element, decide which quantity (m / m² / m³ / count)
    # the cost formula needs, and set the needs_* flags.
    return {}


def _get_meters_node(state: AgentState) -> dict[str, Any]:
    return {
        "pending_tool_calls": [
            {"tool": "grasshopper", "action": "get_meters_by_type", "args": {}}
        ]
    }


def _get_area_node(state: AgentState) -> dict[str, Any]:
    return {
        "pending_tool_calls": [
            {"tool": "grasshopper", "action": "get_area_by_type", "args": {}}
        ]
    }


def _get_volume_node(state: AgentState) -> dict[str, Any]:
    return {
        "pending_tool_calls": [
            {"tool": "grasshopper", "action": "get_volume_by_type", "args": {}}
        ]
    }


def _get_count_node(state: AgentState) -> dict[str, Any]:
    return {
        "pending_tool_calls": [
            {"tool": "grasshopper", "action": "get_count_by_type", "args": {}}
        ]
    }


def _price_gathering_node(state: AgentState) -> dict[str, Any]:
    # Calls readCostDB via the python/cost_db tool.
    return {
        "pending_tool_calls": [
            {"tool": "python", "action": "read_cost_database", "args": {}}
        ]
    }


def _construct_model_node(state: AgentState) -> dict[str, Any]:
    # TODO: combine elements + types + quantities + prices into a cost model.
    # Set model_complete True once everything is filled.
    return {}


def _cost_calculation_node(state: AgentState) -> dict[str, Any]:
    # TODO: sum the per-element costs into a total. Store under baseline_cost
    # or alternative_cost depending on cost_kind.
    return {}


def _budget_variance_check_node(state: AgentState) -> dict[str, Any]:
    # TODO: compare cost to budget and decide branch (baseline -> heatmap,
    # alternative -> delta).
    return {}


def _generate_heatmap_node(state: AgentState) -> dict[str, Any]:
    return {
        "pending_tool_calls": [
            {"tool": "heatmap", "action": "generate", "args": {}}
        ]
    }


def _present_heatmap_node(state: AgentState) -> dict[str, Any]:
    # TODO: format the heatmap into the final response.
    return {"final_response": "Heatmap presented."}


def _calculate_delta_node(state: AgentState) -> dict[str, Any]:
    base = state.get("baseline_cost")
    alt = state.get("alternative_cost")
    if base is not None and alt is not None:
        return {"delta": alt - base}
    return {}


def _generate_rec_node(state: AgentState) -> dict[str, Any]:
    # TODO: produce a recommendation without budget context.
    return {}


def _budget_aware_rec_node(state: AgentState) -> dict[str, Any]:
    # TODO: produce a recommendation that takes the budget into account.
    return {}


def _present_comparison_node(state: AgentState) -> dict[str, Any]:
    # TODO: format the comparison into the final response.
    return {"final_response": "Comparison presented."}


def _modify_price_request_node(state: AgentState) -> dict[str, Any]:
    # Loops back to reasoning with the new request.
    return {"modify_request": False}


# =============================================================================
# Graph wiring — adds nodes and edges according to the Mermaid diagram.
# =============================================================================

def build_graph(ctx: Any) -> Any:
    # The single tool node dispatches to whichever MCP tool was queued
    # (grasshopper / python / cost_db / heatmap). Pending_tool_calls carries
    # the tool name and arguments.
    tool = build_tool_node(ctx.mcp_client, ctx.tools, ctx.edited_layout_path, ctx.cost_db)
    reasoning = _make_reasoning_node(ctx.llm)

    graph = StateGraph(AgentState)

    # --- logical nodes (red + blue boxes) ---
    graph.add_node("reasoning", reasoning)
    graph.add_node("clarify_user", _clarify_user_node)
    graph.add_node("extract_intent", _extract_intent_node)
    graph.add_node("extract_budget", _extract_budget_node)
    graph.add_node("extract_input_data", _extract_input_data_node)
    graph.add_node("layout_processing", _layout_processing_node)
    graph.add_node("getting_layout_json", _getting_layout_json_node)
    graph.add_node("trade_off_advice", _trade_off_advice_node)
    graph.add_node("extract_advice_intent", _extract_advice_intent_node)
    graph.add_node("define_baseline", _define_baseline_node)
    graph.add_node("define_alternative", _define_alternative_node)
    graph.add_node("price_calc_request", _price_calc_request_node)
    graph.add_node("element_identification", _element_identification_node)
    graph.add_node("get_meters", _get_meters_node)
    graph.add_node("get_area", _get_area_node)
    graph.add_node("get_volume", _get_volume_node)
    graph.add_node("get_count", _get_count_node)
    graph.add_node("price_gathering", _price_gathering_node)
    graph.add_node("construct_model", _construct_model_node)
    graph.add_node("cost_calculation", _cost_calculation_node)
    graph.add_node("budget_variance_check", _budget_variance_check_node)
    graph.add_node("generate_heatmap", _generate_heatmap_node)
    graph.add_node("present_heatmap", _present_heatmap_node)
    graph.add_node("calculate_delta", _calculate_delta_node)
    graph.add_node("generate_rec", _generate_rec_node)
    graph.add_node("budget_aware_rec", _budget_aware_rec_node)
    graph.add_node("present_comparison", _present_comparison_node)
    graph.add_node("modify_price_request", _modify_price_request_node)

    # --- single tool node (handles every green box) ---
    graph.add_node("tool", tool)

    # --- entry ---
    graph.add_edge(START, "reasoning")

    # reasoning fans out to clarify / extract_intent / extract_budget / extract_input_data / tool / END
    graph.add_conditional_edges(
        "reasoning",
        _route_reasoning,
        {
            "clarify": "clarify_user",
            "extract_intent": "extract_intent",
            "extract_budget": "extract_budget",
            "extract_input_data": "extract_input_data",
            "finish": END,
            "tool": "tool",
        },
    )

    # clarify -> back to reasoning
    graph.add_edge("clarify_user", "reasoning")

    # extract_intent -> trade_off_advice OR price_calc_request
    graph.add_conditional_edges(
        "extract_intent",
        _route_extract_intent,
        {
            "trade_off_advice": "trade_off_advice",
            "price_calc_request": "price_calc_request",
        },
    )

    # extract_budget -> budget_variance_check (budget context available)
    graph.add_edge("extract_budget", "budget_variance_check")

    # extract_input_data -> layout_processing OR price_calc_request
    graph.add_conditional_edges(
        "extract_input_data",
        _route_extract_input_data,
        {
            "layout_processing": "layout_processing",
            "price_calc_request": "price_calc_request",
        },
    )

    # layout_processing <-> getting_layout_json (tool fetch round-trip)
    graph.add_edge("layout_processing", "getting_layout_json")
    graph.add_edge("getting_layout_json", "tool")
    # The tool node returns to layout_processing once the JSON is fetched.
    # (The tool node should clear pending_tool_calls and route via state.)

    # trade_off_advice -> extract_advice_intent
    graph.add_edge("trade_off_advice", "extract_advice_intent")

    # extract_advice_intent -> define_baseline OR define_alternative
    graph.add_conditional_edges(
        "extract_advice_intent",
        _route_extract_advice_intent,
        {
            "define_baseline": "define_baseline",
            "define_alternative": "define_alternative",
        },
    )

    # baseline / alternative -> price_calc_request
    graph.add_edge("define_baseline", "price_calc_request")
    graph.add_edge("define_alternative", "price_calc_request")

    # price_calc_request -> element_identification OR back to reasoning
    graph.add_conditional_edges(
        "price_calc_request",
        _route_price_calc_request,
        {
            "element_identification": "element_identification",
            "reasoning": "reasoning",
        },
    )

    # element_identification fans out to get_* nodes OR price_gathering
    graph.add_conditional_edges(
        "element_identification",
        _route_element_identification,
        {
            "get_meters": "get_meters",
            "get_area": "get_area",
            "get_volume": "get_volume",
            "get_count": "get_count",
            "price_gathering": "price_gathering",
        },
    )

    # quantity nodes loop back through the tool, then to element_identification
    for q in ("get_meters", "get_area", "get_volume", "get_count"):
        graph.add_edge(q, "tool")
    # The tool node should route back to element_identification after a get_*
    # call (so we keep filling needed quantities until all are present).

    # price_gathering -> tool (read cost DB), then construct_model
    graph.add_edge("price_gathering", "tool")
    # The tool node should route to construct_model once prices are loaded.

    # construct_model -> cost_calculation OR back to reasoning
    graph.add_conditional_edges(
        "construct_model",
        _route_construct_model,
        {
            "cost_calculation": "cost_calculation",
            "reasoning": "reasoning",
        },
    )

    # cost_calculation -> budget_variance_check
    graph.add_edge("cost_calculation", "budget_variance_check")

    # budget_variance_check -> generate_heatmap (baseline) OR calculate_delta (alternative)
    graph.add_conditional_edges(
        "budget_variance_check",
        _route_budget_variance,
        {
            "generate_heatmap": "generate_heatmap",
            "calculate_delta": "calculate_delta",
        },
    )

    # generate_heatmap <-> tool, then present_heatmap
    graph.add_conditional_edges(
        "generate_heatmap",
        _route_generate_heatmap,
        {
            "tool": "tool",
            "present_heatmap": "present_heatmap",
        },
    )

    # present_heatmap -> finish
    graph.add_conditional_edges(
        "present_heatmap",
        _route_present_heatmap,
        {"finish": END},
    )

    # calculate_delta -> generate_rec (no budget) OR budget_aware_rec (with budget)
    graph.add_conditional_edges(
        "calculate_delta",
        _route_calculate_delta,
        {
            "generate_rec": "generate_rec",
            "budget_aware_rec": "budget_aware_rec",
        },
    )

    # both recommendation nodes -> present_comparison
    graph.add_edge("generate_rec", "present_comparison")
    graph.add_edge("budget_aware_rec", "present_comparison")

    # present_comparison -> modify_price_request OR finish
    graph.add_conditional_edges(
        "present_comparison",
        _route_present_comparison,
        {
            "modify_price_request": "modify_price_request",
            "finish": END,
        },
    )

    # modify_price_request -> reasoning
    graph.add_edge("modify_price_request", "reasoning")

    # ------------------------------------------------------------------
    # Tool node return routing
    # ------------------------------------------------------------------
    # The tool node is shared across many call sites. After a tool finishes,
    # it should return to whichever node enqueued the call. We handle that by
    # having the tool node set state["return_to"] before completing, and
    # routing on it here.
    def _route_tool_return(state: AgentState) -> str:
        return state.get("return_to", "reasoning")  # type: ignore[return-value]

    graph.add_conditional_edges(
        "tool",
        _route_tool_return,
        {
            "layout_processing": "layout_processing",
            "element_identification": "element_identification",
            "construct_model": "construct_model",
            "generate_heatmap": "generate_heatmap",
            "reasoning": "reasoning",
        },
    )

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

        # Extra fields default to neutral values.
        "needs_clarification": False,
        "task_known": False,
        "input_data_known": False,
        "intent": None,
        "advice_state": None,
        "budget": None,
        "input_data": None,
        "has_layout": ctx.layout_data is not None,
        "layout_data": ctx.layout_data,
        "element_type_known": False,
        "needs_meters": False,
        "needs_area": False,
        "needs_volume": False,
        "needs_count": False,
        "quantities": {},
        "prices": None,
        "model": None,
        "model_complete": False,
        "cost": None,
        "cost_kind": None,
        "baseline_cost": None,
        "alternative_cost": None,
        "delta": None,
        "has_budget_info": False,
        "heatmap_generated": False,
        "heatmap_path": None,
        "recommendation": None,
        "presented_comparison": False,
        "modify_request": False,
    }


def _format_tool_catalog(tools: list[dict[str, Any]]) -> str:
    lines = []
    for tool in tools:
        name = tool.get("name", "<unknown>")
        description = tool.get("description", "")
        schema = json.dumps(tool.get("inputSchema", {}))
        lines.append(f"- {name}: {description} | inputSchema={schema}")
    return "\n".join(lines)
