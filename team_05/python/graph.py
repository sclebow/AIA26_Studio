from __future__ import annotations
import json
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph

# External Data Connection
# Ensure live_material_api.py has: live_db = MaterialAPI() at the bottom
from live_material_api import live_db

# Existing node builders
from nodes.reason import build_reason_node
from nodes.tools import build_tool_node
from nodes.heatmap_nodes import (
    build_generate_heatmap_node,
    build_present_heatmap_node,
    build_calculate_delta_node
)
from nodes.arch_advice import build_architectural_advice_node

# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    pending_tool_calls: list[dict[str, Any]] | None
    final_response: str | None
    iteration: int
    max_iterations: int
    tool_catalog: str
    layout_json_string: str
    return_to: str | None

    # Routing flags
    needs_clarification: bool
    task_known: bool
    input_data_known: bool
    intent: str | None # "trade_off_advice" | "price_calculation"
    advice_state: str | None # "baseline" | "alternative"

    # Extracted data
    budget: dict[str, Any] | None
    input_data: dict[str, Any] | None
    has_layout: bool
    layout_data: dict[str, Any] | None

    # Price pipeline
    element_type_known: bool
    needs_meters: bool
    needs_area: bool
    needs_volume: bool
    needs_count: bool
    quantities: dict[str, Any]
    prices: dict[str, Any] | None
    model: dict[str, Any] | None
    model_complete: bool
    cost: float | None

    # Variance & Comparison
    cost_kind: str | None # "baseline" | "alternative"
    baseline_cost: float | None
    alternative_cost: float | None
    delta: float | None
    has_budget_info: bool
    heatmap_generated: bool
    heatmap_data: dict[str, Any] | None
    heatmap_json_string: str
    heatmap_path: str | None
    recommendation: str | None
    architectural_advice: str | None
    presented_comparison: bool
    modify_request: bool

# ---------------------------------------------------------------------------
# GLOBAL ROUTING FUNCTIONS (Placed here to avoid NameErrors)
# ---------------------------------------------------------------------------

def _route_reasoning(state: AgentState) -> str:
    if state.get("final_response") is not None:
        return "architectural_advice"
    if state.get("pending_tool_calls"):
        return "tool"
    if state.get("needs_clarification"):
        return "clarify"
    if state.get("task_known"):
        return "extract_intent"
    if state.get("input_data_known"):
        return "extract_input_data"
    return "extract_budget"

def _route_extract_intent(state: AgentState) -> str:
    if state.get("intent") == "trade_off_advice":
        return "trade_off_advice"
    return "price_calc_request"

def _route_extract_input_data(state: AgentState) -> str:
    if state.get("has_layout") and state.get("input_data") is not None:
        return "price_calc_request"
    return "layout_processing"

def _route_extract_advice_intent(state: AgentState) -> str:
    if state.get("advice_state") == "alternative":
        return "define_alternative"
    return "define_baseline"

def _route_price_calc_request(state: AgentState) -> str:
    if state.get("element_type_known"):
        return "element_identification"
    return "reasoning"

def _route_element_identification(state: AgentState) -> str:
    q = state.get("quantities", {})
    if state.get("needs_meters") and "meters" not in q: return "get_meters"
    if state.get("needs_area") and "area" not in q: return "get_area"
    if state.get("needs_volume") and "volume" not in q: return "get_volume"
    if state.get("needs_count") and "count" not in q: return "get_count"
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
    return "tool"

def _route_calculate_delta(state: AgentState) -> str:
    if state.get("has_budget_info"):
        return "budget_aware_rec"
    return "generate_rec"

def _route_tool_return(state: AgentState) -> str:
    return state.get("return_to", "reasoning")

def _route_present_comparison(state: AgentState) -> str:
    if state.get("modify_request"):
        return "modify_price_request"
    return "finish"

# ---------------------------------------------------------------------------
# LOGICAL NODE STUBS
# ---------------------------------------------------------------------------

def _clarify_user_node(state: AgentState) -> dict[str, Any]:
    return {"needs_clarification": False}

def _extract_intent_node(state: AgentState) -> dict[str, Any]:
    return {"task_known": True}

def _extract_budget_node(state: AgentState) -> dict[str, Any]:
    return {"input_data_known": True}

def _extract_input_data_node(state: AgentState) -> dict[str, Any]:
    return {}

def _layout_processing_node(state: AgentState) -> dict[str, Any]:
    return {}

def _getting_layout_json_node(state: AgentState) -> dict[str, Any]:
    return {
        "return_to": "reasoning",
        "pending_tool_calls": [{"name": "get_layout_json", "arguments": {}}]
    }

def _trade_off_advice_node(state: AgentState) -> dict[str, Any]:
    return {}

def _extract_advice_intent_node(state: AgentState) -> dict[str, Any]:
    return {}

def _define_baseline_node(state: AgentState) -> dict[str, Any]:
    return {"cost_kind": "baseline"}

def _define_alternative_node(state: AgentState) -> dict[str, Any]:
    return {"cost_kind": "alternative"}

def _price_calc_request_node(state: AgentState) -> dict[str, Any]:
    return {}

def _element_identification_node(state: AgentState) -> dict[str, Any]:
    return {}

def _get_meters_node(state: AgentState) -> dict[str, Any]:
    return {"return_to": "element_identification", "pending_tool_calls": [{"name": "get_meters_by_type", "arguments": {}}]}

def _get_area_node(state: AgentState) -> dict[str, Any]:
    return {"return_to": "element_identification", "pending_tool_calls": [{"name": "get_area_by_type", "arguments": {}}]}

def _get_volume_node(state: AgentState) -> dict[str, Any]:
    return {"return_to": "element_identification", "pending_tool_calls": [{"name": "get_volume_by_type", "arguments": {}}]}

def _get_count_node(state: AgentState) -> dict[str, Any]:
    return {"return_to": "element_identification", "pending_tool_calls": [{"name": "get_count_by_type", "arguments": {}}]}

def _price_gathering_node(state: AgentState) -> dict[str, Any]:
    print("\n[price_gathering] Fetching live rates from Supabase cloud...")
    
    input_data = state.get("input_data") or {}
    # Let's default to "door" if the LLM doesn't specify
    element_name = input_data.get("element", "door").lower() 
    
    # 1. Fetch the live adjusted rate from your database.
    # We will pass a base price of $500 for a wooden door.
    live_rate = live_db.get_live_rate(element_name, base_rate=500.0)

    return {
        "prices": {element_name: live_rate},
        "return_to": "construct_model"
    }

def _construct_model_node(state: AgentState) -> dict[str, Any]:
    return {"model_complete": True}

def _cost_calculation_node(state: AgentState) -> dict[str, Any]:
    print("\n[cost_calculation] Computing final budget based on Grasshopper layout...")
    
    # 1. Get the data from Grasshopper (via Swiftlet/MCP)
    layout = state.get("layout_data") or {}
    
    # 2. Extract the door count (converting the string "1" to an integer 1)
    door_count_str = layout.get("door_count", "0")
    door_count = int(door_count_str) if str(door_count_str).isdigit() else 0
    
    # 3. Get the live price we just fetched from Supabase
    prices = state.get("prices") or {}
    live_door_price = prices.get("door", 500.0)
    
    # 4. Calculate the total budget
    total_cost = door_count * live_door_price
    
    print("-" * 40)
    print(f"✅ LIVE BUDGET: {door_count} Doors @ ${live_door_price:,.2f} = ${total_cost:,.2f}")
    print("-" * 40)

    # Save the cost to the agent's state so the heatmap node can use it
    return {
        "cost": total_cost,
        "baseline_cost": total_cost, 
        "has_budget_info": True
    }

def _budget_variance_check_node(state: AgentState) -> dict[str, Any]:
    return {}

def _generate_rec_node(state: AgentState) -> dict[str, Any]:
    return {}

def _budget_aware_rec_node(state: AgentState) -> dict[str, Any]:
    return {}

def _present_comparison_node(state: AgentState) -> dict[str, Any]:
    cost_response = state.get("final_response") or state.get("recommendation") or ""
    advice = state.get("architectural_advice") or ""

    parts = [p for p in [cost_response, advice] if p]
    combined = "\n\n---\n\n".join(parts) if parts else "Comparison complete."

    return {"presented_comparison": True, "final_response": combined}

def _modify_price_request_node(state: AgentState) -> dict[str, Any]:
    return {"modify_request": False}

# ---------------------------------------------------------------------------
# GRAPH WIRING
# ---------------------------------------------------------------------------

def build_graph(ctx: Any) -> Any:
    tool_node = build_tool_node(ctx.mcp_client, ctx.tools, ctx.edited_layout_path, ctx.cost_db)
    reasoning_node = build_reason_node(ctx.llm)

    graph = StateGraph(AgentState)

    # 1. Add all nodes
    graph.add_node("reasoning", reasoning_node)
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
    graph.add_node("generate_heatmap", build_generate_heatmap_node())
    graph.add_node("present_heatmap", build_present_heatmap_node())
    graph.add_node("calculate_delta", build_calculate_delta_node())
    graph.add_node("generate_rec", _generate_rec_node)
    graph.add_node("budget_aware_rec", _budget_aware_rec_node)
    graph.add_node("architectural_advice", build_architectural_advice_node())
    graph.add_node("present_comparison", _present_comparison_node)
    graph.add_node("modify_price_request", _modify_price_request_node)
    graph.add_node("tool", tool_node)

    # 2. Add edges (Start -> Reasoning)
    graph.add_edge(START, "reasoning")

    # 3. Conditional reasoning fan-out
    graph.add_conditional_edges("reasoning", _route_reasoning, {
        "clarify": "clarify_user",
        "extract_intent": "extract_intent",
        "extract_budget": "extract_budget",
        "extract_input_data": "extract_input_data",
        "architectural_advice": "architectural_advice",
        "tool": "tool"
    })

    # 4. Intent & Budget branches
    graph.add_edge("clarify_user", "reasoning")
    graph.add_conditional_edges("extract_intent", _route_extract_intent, {
        "trade_off_advice": "trade_off_advice",
        "price_calc_request": "price_calc_request"
    })
    graph.add_edge("extract_budget", "budget_variance_check")
    graph.add_conditional_edges("extract_input_data", _route_extract_input_data, {
        "layout_processing": "layout_processing",
        "price_calc_request": "price_calc_request"
    })

    # 5. Layout fetch loop
    graph.add_edge("layout_processing", "getting_layout_json")
    graph.add_edge("getting_layout_json", "tool")

    # 6. Trade-off Logic
    graph.add_edge("trade_off_advice", "extract_advice_intent")
    graph.add_conditional_edges("extract_advice_intent", _route_extract_advice_intent, {
        "define_baseline": "define_baseline",
        "define_alternative": "define_alternative"
    })
    graph.add_edge("define_baseline", "price_calc_request")
    graph.add_edge("define_alternative", "price_calc_request")

    # 7. Price Calculation Pipeline
    graph.add_conditional_edges("price_calc_request", _route_price_calc_request, {
        "element_identification": "element_identification",
        "reasoning": "reasoning"
    })
    graph.add_conditional_edges("element_identification", _route_element_identification, {
        "get_meters": "get_meters",
        "get_area": "get_area",
        "get_volume": "get_volume",
        "get_count": "get_count",
        "price_gathering": "price_gathering"
    })

    # 8. Quantity gathering -> tool -> identification loop
    for q_node in ["get_meters", "get_area", "get_volume", "get_count"]:
        graph.add_edge(q_node, "tool")

    graph.add_edge("price_gathering", "tool")
    graph.add_conditional_edges("construct_model", _route_construct_model, {
        "cost_calculation": "cost_calculation",
        "reasoning": "reasoning"
    })
    graph.add_edge("cost_calculation", "budget_variance_check")

    # 9. Result Output (Heatmap vs Delta)
    graph.add_conditional_edges("budget_variance_check", _route_budget_variance, {
        "generate_heatmap": "generate_heatmap",
        "calculate_delta": "calculate_delta"
    })

    graph.add_conditional_edges("generate_heatmap", _route_generate_heatmap, {
        "tool": "tool",
        "present_heatmap": "present_heatmap"
    })
    graph.add_edge("present_heatmap", END)

    graph.add_conditional_edges("calculate_delta", _route_calculate_delta, {
        "generate_rec": "generate_rec",
        "budget_aware_rec": "budget_aware_rec"
    })
    graph.add_edge("generate_rec", "architectural_advice")
    graph.add_edge("budget_aware_rec", "architectural_advice")
    graph.add_edge("architectural_advice", "present_comparison")
    graph.add_conditional_edges("present_comparison", _route_present_comparison, {
        "modify_price_request": "modify_price_request",
        "finish": END
    })
    graph.add_edge("modify_price_request", "reasoning")

    # 10. Centralized Tool Router
    graph.add_conditional_edges("tool", _route_tool_return, {
        "layout_processing": "layout_processing",
        "element_identification": "element_identification",
        "construct_model": "construct_model",
        "generate_heatmap": "generate_heatmap",
        "reasoning": "reasoning"
    })

    return graph.compile()

# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def run_agent(prompt: str, ctx: Any) -> str:
    app = build_graph(ctx)
    
    # Use your helper function to properly build the state, including the tool_catalog!
    initial_state = _build_initial_state(prompt, ctx)

    final_state = app.invoke(initial_state)
    return final_state.get("final_response", "Process completed without summary.")

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
        "heatmap_data": None,
        "heatmap_json_string": "",
        "heatmap_path": None,
        "recommendation": None,
        "architectural_advice": None,
        "presented_comparison": False,
        "modify_request": False,
    }


def _format_tool_catalog(tools: list[dict[str, Any]]) -> str:
    lines = []
    for tool in tools:
        name = tool.get("name", "<unknown>")
        description = tool.get("description", "")
        schema = json.dumps(tool.get("inputSchema", {}))
        lines.append(f"- **Tool name: '{name}'**\n  Description: {description}\n  Input schema: {schema}")
    return "\n".join(lines)
