from __future__ import annotations

import json
from typing import Any

from langgraph.graph import END, START, StateGraph

from .decision_engine import DecisionEngine, Planner, RuleBasedPlanner
from .mcp_client import ToolClient
from .models import PlanStep, RoutingDecision
from .state import AgentState, build_initial_state
from .tool_catalog import ToolCatalog


def build_agent_graph(
    decision_engine: DecisionEngine,
    tool_client: ToolClient,
    catalog: ToolCatalog,
    planner: Planner | None = None,
) -> Any:
    active_planner = planner or RuleBasedPlanner()
    graph = StateGraph(AgentState)

    graph.add_node("planner", _build_planner_node(active_planner, catalog))
    graph.add_node("central_reason", _build_central_reason_node(decision_engine, catalog))
    graph.add_node("read_site", _build_group_executor(tool_client, catalog, "read_site"))
    graph.add_node("generate_shape", _build_group_executor(tool_client, catalog, "generate_shape"))
    graph.add_node("check_requested_position", _build_requested_position_node(tool_client, catalog))
    graph.add_node("check_constraints", _build_constraint_node(tool_client, catalog))
    graph.add_node("optimize", _build_group_executor(tool_client, catalog, "optimize"))
    graph.add_node("evaluate", _build_evaluation_node(tool_client, catalog))
    graph.add_node("place_building", _build_place_building_node(tool_client, catalog))
    graph.add_node("analyze_remaining_positions", _build_remaining_positions_node(tool_client, catalog))
    graph.add_node("await_human", _build_await_human_node())
    graph.add_node("report", _build_report_node(decision_engine))
    graph.add_node("finish", lambda state: state)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner",
        _route_from_planner,
        {
            "central_reason": "central_reason",
            "finish": "finish",
        },
    )
    graph.add_conditional_edges(
        "central_reason",
        _route_from_central_reason,
        {
            "read_site": "read_site",
            "generate_shape": "generate_shape",
            "check_requested_position": "check_requested_position",
            "check_constraints": "check_constraints",
            "optimize": "optimize",
            "evaluate": "evaluate",
            "place_building": "place_building",
            "analyze_remaining_positions": "analyze_remaining_positions",
            "await_human": "await_human",
            "report": "report",
            "finish": "finish",
        },
    )

    for node_name in [
        "read_site",
        "generate_shape",
        "check_requested_position",
        "check_constraints",
        "optimize",
        "evaluate",
        "place_building",
        "analyze_remaining_positions",
    ]:
        graph.add_edge(node_name, "planner")

    graph.add_edge("await_human", "finish")
    graph.add_edge("report", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


def run_agent(
    user_prompt: str,
    decision_engine: DecisionEngine,
    tool_client: ToolClient,
    catalog: ToolCatalog,
    initial_layout: dict[str, Any] | None = None,
    max_optimization_cycles: int = 4,
    planner: Planner | None = None,
) -> AgentState:
    app = build_agent_graph(decision_engine, tool_client, catalog, planner=planner)
    initial_state = build_initial_state(
        user_prompt=user_prompt,
        layout_payload=initial_layout,
        max_optimization_cycles=max_optimization_cycles,
    )
    return app.invoke(initial_state)


def _build_planner_node(planner: Planner, catalog: ToolCatalog):
    def planner_node(state: AgentState) -> AgentState:
        plan_steps = planner.build_plan(state, catalog)
        plan_payload = [step.to_state() for step in plan_steps]
        active_step = next((step for step in plan_steps if step.status == "pending"), None)

        messages = list(state.get("messages", []))
        if state.get("replan_required") or not state.get("plan"):
            reason = state.get("replan_reason") or "Plan refreshed."
            messages.append(f"Planner updated the task sequence: {reason}")

        update: AgentState = {
            "plan": plan_payload,
            "active_step_id": active_step.step_id if active_step else None,
            "current_action": active_step.action if active_step else "finish",
            "decision_reason": active_step.goal if active_step else "No pending steps remain.",
            "replan_required": False,
            "replan_reason": None,
            "messages": messages,
        }

        if active_step is None and not state.get("final_response"):
            update["final_response"] = "Workflow completed without any pending plan steps."

        return update

    return planner_node


def _build_central_reason_node(
    decision_engine: DecisionEngine,
    catalog: ToolCatalog,
):
    def central_reason(state: AgentState) -> AgentState:
        active_step = _get_active_step(state)
        if active_step is None:
            return {
                "current_action": "finish",
                "decision_reason": "No active step available.",
                "pending_tool_calls": [],
            }

        if active_step.action in {
            "read_site",
            "check_requested_position",
            "check_constraints",
            "evaluate",
            "place_building",
            "analyze_remaining_positions",
            "report",
            "await_human",
            "finish",
        }:
            decision = _deterministic_step_decision(state, active_step)
        else:
            decision = decision_engine.decide(state, catalog, active_step)

        guarded = _apply_step_guard(state, decision, catalog, active_step)
        messages = list(state.get("messages", []))
        messages.append(f"Supervisor decision: {guarded.action} | {guarded.reasoning}")
        return {
            "current_action": guarded.action,
            "decision_reason": guarded.reasoning,
            "pending_tool_calls": [
                {"name": tool_call.name, "arguments": dict(tool_call.arguments)}
                for tool_call in guarded.tool_calls
            ],
            "human_request": guarded.user_question or state.get("human_request"),
            "messages": messages,
        }

    return central_reason


def _build_group_executor(
    tool_client: ToolClient,
    catalog: ToolCatalog,
    action: str,
):
    def execute_group(state: AgentState) -> AgentState:
        allowed_names = set(catalog.names_for_action(action))
        pending_calls = state.get("pending_tool_calls", [])
        tool_calls = pending_calls
        if action == "read_site" or not tool_calls:
            tool_calls = [{"name": name, "arguments": {}} for name in allowed_names]

        previous_geometry = state.get("geometry_id")
        records, aggregate, layout_json, geometry_id = _execute_tool_calls(
            tool_client=tool_client,
            tool_calls=tool_calls,
            allowed_names=allowed_names,
            layout_json=state.get("layout_json", "{}"),
            geometry_id=state.get("geometry_id"),
        )
        messages = list(state.get("messages", []))
        messages.extend(record["message"] for record in records)
        tool_history = list(state.get("tool_history", []))
        tool_history.extend(records)

        update: AgentState = {
            "messages": messages,
            "tool_history": tool_history,
            "pending_tool_calls": [],
            "layout_json": layout_json,
            "replan_required": True,
            "replan_reason": f"{action} step finished.",
            "human_request": None,
        }
        if geometry_id is not None:
            update["geometry_id"] = geometry_id

        if action == "read_site":
            update["site_context"] = aggregate
            if not aggregate:
                update["error"] = "Site-reading tools returned no context."
                update["replan_reason"] = "Site-reading tools returned no usable context."
        elif action == "generate_shape":
            update["shape_context"] = aggregate if _aggregate_contains_boundary(aggregate) else state.get("shape_context", {})
            update["constraint_results"] = {}
            update["checked_geometry_id"] = None
            update["violations"] = []
            update["evaluation_results"] = {}
            update["requested_position_assessment"] = {}
            if geometry_id is None or geometry_id == previous_geometry:
                update["error"] = "Shape generation did not produce a new geometry."
                update["replan_reason"] = "Shape generation did not produce a usable geometry revision."
            else:
                update["error"] = None
                update["replan_reason"] = "Generated a new geometry candidate."
        elif action == "optimize":
            if _aggregate_contains_boundary(aggregate):
                update["shape_context"] = aggregate
            else:
                merged_shape_context = dict(state.get("shape_context", {}))
                merged_shape_context.update(aggregate)
                update["shape_context"] = merged_shape_context
            update["optimization_cycles"] = state.get("optimization_cycles", 0) + 1
            update["constraint_results"] = {}
            update["checked_geometry_id"] = None
            update["violations"] = []
            update["evaluation_results"] = {}
            update["requested_position_assessment"] = {}
            if geometry_id is None or geometry_id == previous_geometry:
                update["error"] = "Optimization did not produce a new geometry revision."
                update["replan_reason"] = "Optimization failed to change the geometry; replanning required."
            else:
                update["error"] = None
                update["replan_reason"] = "Optimization produced a new geometry revision."

        return update

    return execute_group


def _build_constraint_node(
    tool_client: ToolClient,
    catalog: ToolCatalog,
):
    def check_constraints(state: AgentState) -> AgentState:
        allowed_names = set(catalog.names_for_action("check_constraints"))
        tool_calls = [{"name": name, "arguments": {}} for name in allowed_names]
        records, aggregate, layout_json, geometry_id = _execute_tool_calls(
            tool_client=tool_client,
            tool_calls=tool_calls,
            allowed_names=allowed_names,
            layout_json=state.get("layout_json", "{}"),
            geometry_id=state.get("geometry_id"),
        )
        messages = list(state.get("messages", []))
        messages.extend(record["message"] for record in records)
        tool_history = list(state.get("tool_history", []))
        tool_history.extend(records)
        violations = _extract_violations(aggregate)
        messages.append(f"Constraint summary: {violations or ['none']}")
        update: AgentState = {
            "messages": messages,
            "tool_history": tool_history,
            "constraint_results": aggregate,
            "checked_geometry_id": geometry_id,
            "violations": violations,
            "layout_json": layout_json,
            "pending_tool_calls": [],
            "replan_required": True,
            "replan_reason": "Constraint results changed the remaining execution plan.",
            "error": None,
        }
        if geometry_id is not None:
            update["geometry_id"] = geometry_id
        if violations and state.get("optimization_cycles", 0) >= state.get("max_optimization_cycles", 0):
            update["replan_reason"] = "Maximum optimization cycles reached with remaining violations."
        return update

    return check_constraints


def _build_evaluation_node(
    tool_client: ToolClient,
    catalog: ToolCatalog,
):
    def evaluate(state: AgentState) -> AgentState:
        allowed_names = set(catalog.names_for_action("evaluate"))
        tool_calls = [{"name": name, "arguments": {}} for name in allowed_names]
        records, aggregate, layout_json, geometry_id = _execute_tool_calls(
            tool_client=tool_client,
            tool_calls=tool_calls,
            allowed_names=allowed_names,
            layout_json=state.get("layout_json", "{}"),
            geometry_id=state.get("geometry_id"),
        )
        messages = list(state.get("messages", []))
        messages.extend(record["message"] for record in records)
        tool_history = list(state.get("tool_history", []))
        tool_history.extend(records)
        update: AgentState = {
            "messages": messages,
            "tool_history": tool_history,
            "evaluation_results": aggregate,
            "layout_json": layout_json,
            "pending_tool_calls": [],
            "replan_required": True,
            "replan_reason": "Evaluation completed; final reporting can now be planned.",
            "error": None,
        }
        if geometry_id is not None:
            update["geometry_id"] = geometry_id
        return update

    return evaluate


def _build_requested_position_node(
    tool_client: ToolClient,
    catalog: ToolCatalog,
):
    def check_requested_position(state: AgentState) -> AgentState:
        allowed_names = set(catalog.names_for_action("check_requested_position"))
        tool_name = "requested_position_checker_04"
        if tool_name not in allowed_names:
            return {
                "requested_position_assessment": {},
                "replan_required": True,
                "replan_reason": "Requested-position tool unavailable; continuing without geometric point check.",
            }

        boundary = _extract_current_boundary(state)
        site_boundary = _extract_site_boundary(state)
        requested_point = _extract_requested_position(state)
        if not boundary or not site_boundary or not requested_point:
            return {
                "requested_position_assessment": {},
                "replan_required": True,
                "replan_reason": "Requested-position inputs incomplete; planner will continue without this check.",
            }

        raw_output = tool_client.call_tool(
            tool_name,
            {
                "site_boundary": site_boundary,
                "placed_buildings": state.get("placed_buildings", []),
                "proposed_boundary": boundary,
                "requested_point": requested_point,
                "candidate_positions": state.get("remaining_candidate_positions", []),
            },
        )
        parsed_output = _parse_tool_output(raw_output)
        messages = list(state.get("messages", []))
        tool_history = list(state.get("tool_history", []))
        assessment = parsed_output.get("data", {}) if isinstance(parsed_output, dict) else {}
        if isinstance(assessment, dict):
            assessment = dict(assessment)
            assessment["geometry_id"] = state.get("geometry_id")
        tool_history.append(
            {
                "tool": tool_name,
                "arguments": {
                    "requested_point": requested_point,
                },
                "output": parsed_output,
                "message": f"Tool {tool_name} executed.",
            }
        )
        messages.append(f"Tool {tool_name} executed.")
        return {
            "messages": messages,
            "tool_history": tool_history,
            "requested_position_assessment": assessment,
            "replan_required": True,
            "replan_reason": "Requested-position analysis completed.",
            "error": None,
        }

    return check_requested_position


def _build_place_building_node(
    tool_client: ToolClient,
    catalog: ToolCatalog,
):
    def place_building(state: AgentState) -> AgentState:
        allowed_names = set(catalog.names_for_action("place_building"))
        tool_name = "import_building_boundary_04"
        boundary = _extract_placed_boundary(state)
        geometry_id = state.get("geometry_id")
        if tool_name not in allowed_names or not boundary or not geometry_id:
            return {
                "replan_required": True,
                "replan_reason": "Placement inputs unavailable; skipping building placement.",
            }

        raw_output = tool_client.call_tool(
            tool_name,
            {
                "geometry_id": geometry_id,
                "boundary": boundary,
            },
        )
        parsed_output = _parse_tool_output(raw_output)
        placement_data = parsed_output.get("data", {}) if isinstance(parsed_output, dict) else {}
        placed_buildings = list(state.get("placed_buildings", []))
        placed_buildings.append(
            {
                "geometry_id": geometry_id,
                "boundary": boundary,
                "placement": placement_data,
            }
        )
        messages = list(state.get("messages", []))
        messages.append(f"Tool {tool_name} executed.")
        tool_history = list(state.get("tool_history", []))
        tool_history.append(
            {
                "tool": tool_name,
                "arguments": {"geometry_id": geometry_id},
                "output": parsed_output,
                "message": f"Tool {tool_name} executed.",
            }
        )

        target_count = int(state.get("target_building_count", 1) or 1)
        more_buildings_needed = len(placed_buildings) < target_count
        update: AgentState = {
            "messages": messages,
            "tool_history": tool_history,
            "placed_buildings": placed_buildings,
            "replan_required": True,
            "replan_reason": "Building placement completed.",
            "error": None,
        }
        if more_buildings_needed:
            update.update(
                {
                    "geometry_id": None,
                    "checked_geometry_id": None,
                    "shape_context": {},
                    "constraint_results": {},
                    "violations": [],
                    "evaluation_results": {},
                    "requested_position_assessment": {},
                }
            )
        return update

    return place_building


def _build_remaining_positions_node(
    tool_client: ToolClient,
    catalog: ToolCatalog,
):
    def analyze_remaining_positions(state: AgentState) -> AgentState:
        allowed_names = set(catalog.names_for_action("analyze_remaining_positions"))
        tool_name = "remaining_buildable_positions_04"
        site_boundary = _extract_site_boundary(state)
        if tool_name not in allowed_names or not site_boundary:
            return {
                "replan_required": True,
                "replan_reason": "Remaining-position inputs unavailable; continuing without candidate positions.",
            }

        boundary = _extract_current_boundary(state)
        raw_output = tool_client.call_tool(
            tool_name,
            {
                "site_boundary": site_boundary,
                "placed_buildings": state.get("placed_buildings", []),
                "candidate_building_boundary": boundary,
            },
        )
        parsed_output = _parse_tool_output(raw_output)
        result_data = parsed_output.get("data", {}) if isinstance(parsed_output, dict) else {}
        messages = list(state.get("messages", []))
        messages.append(f"Tool {tool_name} executed.")
        tool_history = list(state.get("tool_history", []))
        tool_history.append(
            {
                "tool": tool_name,
                "arguments": {"placed_buildings": len(state.get("placed_buildings", []))},
                "output": parsed_output,
                "message": f"Tool {tool_name} executed.",
            }
        )
        return {
            "messages": messages,
            "tool_history": tool_history,
            "remaining_candidate_positions": result_data.get("candidate_positions", []) if isinstance(result_data, dict) else [],
            "replan_required": True,
            "replan_reason": "Remaining-site analysis completed.",
            "error": None,
        }

    return analyze_remaining_positions


def _build_await_human_node():
    def await_human(state: AgentState) -> AgentState:
        question = state.get("human_request") or "Additional user clarification is required."
        messages = list(state.get("messages", []))
        messages.append(f"Awaiting human input: {question}")
        return {
            "messages": messages,
            "final_response": question,
            "replan_required": False,
            "replan_reason": None,
        }

    return await_human


def _build_report_node(decision_engine: DecisionEngine):
    def report(state: AgentState) -> AgentState:
        report_text = decision_engine.build_report(state)
        messages = list(state.get("messages", []))
        messages.append("Final report generated.")
        return {
            "messages": messages,
            "final_response": report_text,
            "replan_required": False,
            "replan_reason": None,
        }

    return report


def _route_from_planner(state: AgentState) -> str:
    if state.get("active_step_id"):
        return "central_reason"
    return "finish"


def _route_from_central_reason(state: AgentState) -> str:
    return state.get("current_action", "finish")


def _get_active_step(state: AgentState) -> PlanStep | None:
    active_step_id = state.get("active_step_id")
    plan_payload = state.get("plan", [])
    for step_payload in plan_payload:
        step = PlanStep.from_state(step_payload)
        if step.step_id == active_step_id:
            return step
    return None


def _deterministic_step_decision(state: AgentState, active_step: PlanStep) -> RoutingDecision:
    if active_step.action == "await_human":
        question = str(state.get("human_request") or active_step.goal).strip()
        return RoutingDecision(
            action="await_human",
            reasoning=active_step.goal,
            user_question=question,
        )
    return RoutingDecision(action=active_step.action, reasoning=active_step.goal)


def _apply_step_guard(
    state: AgentState,
    decision: RoutingDecision,
    catalog: ToolCatalog,
    active_step: PlanStep,
) -> RoutingDecision:
    del state

    if decision.action == "await_human":
        return decision

    if active_step.action in {
        "read_site",
        "check_requested_position",
        "check_constraints",
        "evaluate",
        "place_building",
        "analyze_remaining_positions",
        "report",
        "await_human",
        "finish",
    }:
        return RoutingDecision(
            action=active_step.action,
            reasoning=decision.reasoning or active_step.goal,
            user_question=decision.user_question,
        )

    if decision.action != active_step.action:
        decision = RoutingDecision(
            action=active_step.action,
            reasoning=decision.reasoning or active_step.goal,
            tool_calls=decision.tool_calls,
            user_question=decision.user_question,
        )

    allowed_names = set(catalog.names_for_action(active_step.action))
    filtered_calls = tuple(tool_call for tool_call in decision.tool_calls if tool_call.name in allowed_names)
    return RoutingDecision(
        action=active_step.action,
        reasoning=decision.reasoning or active_step.goal,
        tool_calls=filtered_calls,
        user_question=decision.user_question,
    )


def _execute_tool_calls(
    tool_client: ToolClient,
    tool_calls: list[dict[str, Any]],
    allowed_names: set[str],
    layout_json: str,
    geometry_id: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], str, str | None]:
    records: list[dict[str, Any]] = []
    aggregate: dict[str, Any] = {}
    current_layout_json = layout_json
    current_geometry_id = geometry_id

    for tool_call in tool_calls:
        tool_name = str(tool_call.get("name", "")).strip()
        if tool_name not in allowed_names:
            continue
        raw_arguments = tool_call.get("arguments", {})
        arguments = dict(raw_arguments) if isinstance(raw_arguments, dict) else {}
        arguments = {key: value for key, value in arguments.items() if value is not None}
        if "layout_json" not in arguments:
            arguments["layout_json"] = current_layout_json
        if current_geometry_id and "geometry_id" not in arguments:
            arguments["geometry_id"] = current_geometry_id

        raw_output = tool_client.call_tool(tool_name, arguments)
        parsed_output = _parse_tool_output(raw_output)
        aggregate[tool_name] = parsed_output
        current_geometry_id = _extract_geometry_id(parsed_output) or current_geometry_id
        if isinstance(parsed_output, dict) and parsed_output:
            current_layout_json = json.dumps(parsed_output)

        records.append(
            {
                "tool": tool_name,
                "arguments": arguments,
                "output": parsed_output,
                "message": f"Tool {tool_name} executed.",
            }
        )

    return records, aggregate, current_layout_json, current_geometry_id


def _parse_tool_output(raw_output: str) -> Any:
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        return {"raw_text": raw_output}


def _extract_geometry_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        if isinstance(payload.get("geometry_id"), str):
            return payload["geometry_id"]
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("geometry_id"), str):
            return data["geometry_id"]
        for value in payload.values():
            geometry_id = _extract_geometry_id(value)
            if geometry_id:
                return geometry_id
    if isinstance(payload, list):
        for item in payload:
            geometry_id = _extract_geometry_id(item)
            if geometry_id:
                return geometry_id
    return None


def _extract_current_boundary(state: AgentState) -> list[list[float]] | None:
    shape_context = state.get("shape_context", {})
    if not isinstance(shape_context, dict):
        shape_context = {}
    for payload in shape_context.values():
        if isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, dict) and isinstance(data.get("boundary"), list):
                return data["boundary"]
    for record in reversed(state.get("tool_history", [])):
        if not isinstance(record, dict):
            continue
        output = record.get("output")
        if isinstance(output, dict):
            data = output.get("data", output)
            if isinstance(data, dict) and isinstance(data.get("boundary"), list):
                return data["boundary"]
    return None


def _aggregate_contains_boundary(aggregate: dict[str, Any]) -> bool:
    for payload in aggregate.values():
        if isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, dict) and isinstance(data.get("boundary"), list):
                return True
    return False


def _extract_placed_boundary(state: AgentState) -> list[list[float]] | None:
    assessment = state.get("requested_position_assessment", {})
    if isinstance(assessment, dict) and isinstance(assessment.get("translated_boundary"), list):
        return assessment["translated_boundary"]
    return _extract_current_boundary(state)


def _extract_site_boundary(state: AgentState) -> list[list[float]] | None:
    if isinstance(state.get("site_boundary"), list) and state.get("site_boundary"):
        return state.get("site_boundary")
    try:
        layout_payload = json.loads(state.get("layout_json", "{}"))
    except json.JSONDecodeError:
        return None
    boundary = layout_payload.get("site_boundary") if isinstance(layout_payload, dict) else None
    return boundary if isinstance(boundary, list) else None


def _extract_requested_position(state: AgentState) -> list[float] | None:
    requested_positions = state.get("requested_positions", [])
    if not isinstance(requested_positions, list):
        return None
    placed_building_count = len(state.get("placed_buildings", []))
    if 0 <= placed_building_count < len(requested_positions):
        point = requested_positions[placed_building_count]
        if isinstance(point, list) and len(point) >= 2:
            return [float(point[0]), float(point[1])]
    return None


def _extract_violations(results: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for tool_name, payload in results.items():
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            continue
        if tool_name == "site_fit_checker_04" and not data.get("fits", data.get("fits_within_site", True)):
            violations.append("fit")
        elif tool_name == "setback_checker_04" and not data.get("compliant", True):
            violations.append("setback")
        elif tool_name == "area_requirement_checker_04" and not data.get("gfa_compliant", data.get("meets_requirement", True)):
            violations.append("area")
        elif tool_name == "adjacency_access_checker_04" and not data.get("road_access_ok", data.get("access_adequate", True)):
            violations.append("access")
        elif tool_name == "tree_constraint_checker_04" and not data.get("no_conflicts", True):
            violations.append("trees")
    return violations