from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_openai import ChatOpenAI

from .models import PlanStep, RoutingDecision
from .models import ToolCall
from .tools.generate_building_boundary import get_boundary_planning_defaults
from .tool_catalog import ToolCatalog


SUPERVISOR_PROMPT = """
You are the execution supervisor for one active plan step in a site design LangGraph agent.

Active step:
{active_step}

Supervisor rules:
- Only act on the active step.
- If the active step is `generate_shape`, return `generate_shape` with one or more valid shape-generation tool calls.
- For `generate_shape`, never return an empty `tool_calls` array.
- For `generate_shape`, include all required arguments for the selected tool.
- If you choose `generate_building_boundary`, you must provide `area`.
- If tool parameter defaults are shown in the catalog, use them for omitted optional arguments rather than inventing new values.
- If the active step is `optimize`, return `optimize` with one or more valid manipulation tool calls.
- If the active step is `check_requested_position`, `place_building`, or `analyze_remaining_positions`, do not invent a different phase.
- Use `await_human` only if the active step cannot proceed without clarification.
- Do not switch to other workflow phases. Planning is handled elsewhere.

Return JSON only with this shape:
{{
    "action": "generate_shape|optimize|check_requested_position|place_building|analyze_remaining_positions|await_human",
  "reasoning": "short explanation",
  "user_question": "only for await_human, else empty string",
  "tool_calls": [{{"name": "tool_name", "arguments": {{}}}}]
}}

Relevant tool catalog:
{tool_catalog}

State snapshot:
{state_snapshot}
"""


REPORT_PROMPT = """
You are writing the final report for a site design agent.
Summarize the chosen geometry, remaining constraint state, evaluation results, and next recommendation.
Keep it concise and concrete.

State snapshot:
{state_snapshot}
"""


class Planner(Protocol):
    def build_plan(self, state: dict[str, Any], catalog: ToolCatalog) -> tuple[PlanStep, ...]:
        ...


class DecisionEngine(Protocol):
    def decide(
        self,
        state: dict[str, Any],
        catalog: ToolCatalog,
        active_step: PlanStep,
    ) -> RoutingDecision:
        ...

    def build_report(self, state: dict[str, Any]) -> str:
        ...


@dataclass(frozen=True)
class RuleBasedPlanner:
    def build_plan(self, state: dict[str, Any], catalog: ToolCatalog) -> tuple[PlanStep, ...]:
        del catalog

        workflow_mode = str(state.get("workflow_mode", "full") or "full").strip().lower()
        placed_buildings = list(state.get("placed_buildings", []))
        target_building_count = max(1, int(state.get("target_building_count", 1) or 1))
        current_building_index = min(len(placed_buildings) + 1, target_building_count)
        current_building_label = _format_building_label(current_building_index)
        requested_positions = list(state.get("requested_positions", []))
        building_intents = list(state.get("building_intents", []))
        active_requested_position = (
            requested_positions[current_building_index - 1]
            if 0 <= current_building_index - 1 < len(requested_positions)
            else None
        )
        active_building_intent = (
            str(building_intents[current_building_index - 1]).strip()
            if 0 <= current_building_index - 1 < len(building_intents)
            else ""
        )
        intent_suffix = f" Intent: {active_building_intent}" if active_building_intent else ""
        geometry_id = state.get("geometry_id")
        checked_geometry_id = state.get("checked_geometry_id")
        current_geometry_checked = bool(
            geometry_id
            and checked_geometry_id == geometry_id
            and state.get("constraint_results")
        )
        violations = list(state.get("violations", []))
        optimization_cycles = int(state.get("optimization_cycles", 0) or 0)
        max_cycles = int(state.get("max_optimization_cycles", 0) or 0)
        maxed_out = bool(violations) and optimization_cycles >= max_cycles
        report_complete = bool(state.get("final_response"))
        await_question = str(state.get("human_request") or "").strip()
        requested_position_assessment = state.get("requested_position_assessment") or {}
        assessment_geometry_id = requested_position_assessment.get("geometry_id") if isinstance(requested_position_assessment, dict) else None
        requested_position_checked = bool(geometry_id and assessment_geometry_id == geometry_id)
        remaining_positions_ready = bool(state.get("remaining_candidate_positions"))
        more_buildings_needed = len(placed_buildings) < target_building_count
        current_geometry_already_placed = any(
            isinstance(item, dict) and item.get("geometry_id") == geometry_id
            for item in placed_buildings
        )
        can_place_current_building = bool(
            geometry_id
            and current_geometry_checked
            and not violations
            and (not active_requested_position or requested_position_checked)
            and not current_geometry_already_placed
        )
        report_ready = bool(state.get("evaluation_results")) and (not more_buildings_needed or not geometry_id)

        if workflow_mode == "boundary_only":
            return (
                PlanStep(
                    step_id="read_site",
                    action="read_site",
                    goal="Load site boundary, context, and legal constraints.",
                    status="completed" if state.get("site_context") else "pending",
                ),
                PlanStep(
                    step_id="generate_shape",
                    action="generate_shape",
                    goal=f"Create the boundary candidate for {current_building_label}.{intent_suffix}",
                    status="completed" if geometry_id else ("pending" if state.get("site_context") else "skipped"),
                ),
                PlanStep(
                    step_id="check_requested_position",
                    action="check_requested_position",
                    goal=f"Check whether the user's requested position works for {current_building_label}.{intent_suffix}",
                    status="skipped",
                ),
                PlanStep(
                    step_id="check_constraints",
                    action="check_constraints",
                    goal=f"Validate the current geometry for {current_building_label} against all constraints.{intent_suffix}",
                    status="skipped",
                ),
                PlanStep(
                    step_id="optimize",
                    action="optimize",
                    goal=f"Repair the highest-priority violations on {current_building_label}.{intent_suffix}",
                    status="skipped",
                ),
                PlanStep(
                    step_id="evaluate",
                    action="evaluate",
                    goal=f"Evaluate {current_building_label} for design quality and performance.{intent_suffix}",
                    status="skipped",
                ),
                PlanStep(
                    step_id="place_building",
                    action="place_building",
                    goal=f"Place {current_building_label} into Rhino/Grasshopper.{intent_suffix}",
                    status="skipped",
                ),
                PlanStep(
                    step_id="analyze_remaining_positions",
                    action="analyze_remaining_positions",
                    goal=f"Analyze the remaining site area after placing {current_building_label}.{intent_suffix}",
                    status="skipped",
                ),
                PlanStep(
                    step_id="await_human",
                    action="await_human",
                    goal=await_question or "Ask the user for missing clarification.",
                    status="completed" if await_question and report_complete else ("pending" if await_question else "skipped"),
                ),
                PlanStep(
                    step_id="report",
                    action="report",
                    goal="Write the design report for the current best state.",
                    status=(
                        "completed"
                        if report_complete and not await_question
                        else ("pending" if geometry_id or state.get("error") else "skipped")
                    ),
                ),
            )

        return (
            PlanStep(
                step_id="read_site",
                action="read_site",
                goal="Load site boundary, context, and legal constraints.",
                status="completed" if state.get("site_context") else "pending",
            ),
            PlanStep(
                step_id="generate_shape",
                action="generate_shape",
                goal=f"Create the next geometry candidate for {current_building_label}.{intent_suffix}",
                status=(
                    "completed"
                    if geometry_id
                    else (
                        "pending"
                        if state.get("site_context")
                        and more_buildings_needed
                        and (not placed_buildings or remaining_positions_ready)
                        else "skipped"
                    )
                ),
            ),
            PlanStep(
                step_id="check_requested_position",
                action="check_requested_position",
                goal=f"Check whether the user's requested position works for {current_building_label}.{intent_suffix}",
                status=(
                    "completed"
                    if requested_position_checked or not active_requested_position
                    else ("pending" if geometry_id else "skipped")
                ),
            ),
            PlanStep(
                step_id="check_constraints",
                action="check_constraints",
                goal=f"Validate the current geometry for {current_building_label} against all constraints.{intent_suffix}",
                status="completed" if current_geometry_checked else ("pending" if geometry_id else "skipped"),
            ),
            PlanStep(
                step_id="optimize",
                action="optimize",
                goal=f"Repair the highest-priority violations on {current_building_label}.{intent_suffix}",
                status="pending" if violations and not maxed_out else "skipped",
            ),
            PlanStep(
                step_id="evaluate",
                action="evaluate",
                goal=f"Evaluate {current_building_label} for design quality and performance.{intent_suffix}",
                status=(
                    "completed"
                    if state.get("evaluation_results")
                    else ("pending" if current_geometry_checked and not violations else "skipped")
                ),
            ),
            PlanStep(
                step_id="place_building",
                action="place_building",
                goal=f"Place {current_building_label} into Rhino/Grasshopper.{intent_suffix}",
                status=(
                    "completed"
                    if current_geometry_already_placed
                    else ("pending" if can_place_current_building else "skipped")
                ),
            ),
            PlanStep(
                step_id="analyze_remaining_positions",
                action="analyze_remaining_positions",
                goal=f"Analyze the remaining site area after placing {current_building_label}.{intent_suffix}",
                status=(
                    "completed"
                    if remaining_positions_ready
                    else ("pending" if placed_buildings and more_buildings_needed else "skipped")
                ),
            ),
            PlanStep(
                step_id="await_human",
                action="await_human",
                goal=await_question or "Ask the user for missing clarification.",
                status="completed" if await_question and report_complete else ("pending" if await_question else "skipped"),
            ),
            PlanStep(
                step_id="report",
                action="report",
                goal="Write the design report for the current best state.",
                status=(
                    "completed"
                    if report_complete and not await_question
                    else (
                        "pending"
                        if report_ready or maxed_out or state.get("error")
                        else "skipped"
                    )
                ),
            ),
        )


@dataclass
class OpenAIDecisionEngine:
    llm: ChatOpenAI

    def decide(
        self,
        state: dict[str, Any],
        catalog: ToolCatalog,
        active_step: PlanStep,
    ) -> RoutingDecision:
        snapshot = _build_state_snapshot(state)
        content = self._invoke_json(
            system_prompt=SUPERVISOR_PROMPT.format(
                active_step=json.dumps(active_step.to_state(), indent=2),
                tool_catalog=catalog.render_for_action(active_step.action),
                state_snapshot=json.dumps(snapshot, indent=2),
            ),
            user_prompt=state.get("user_prompt", ""),
        )
        decision = RoutingDecision.from_payload(content)
        return _repair_generate_shape_decision(decision, state, catalog, active_step)

    def build_report(self, state: dict[str, Any]) -> str:
        snapshot = _build_state_snapshot(state)
        messages = [
            {"role": "system", "content": REPORT_PROMPT.format(state_snapshot=json.dumps(snapshot, indent=2))},
            {"role": "user", "content": state.get("user_prompt", "")},
        ]
        result = self.llm.invoke(messages)
        return _normalize_content(result.content).strip()

    def _invoke_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        result = self.llm.invoke(messages)
        content = _normalize_content(result.content)
        return _parse_json_object(content)


def _build_state_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan": state.get("plan", []),
        "active_step_id": state.get("active_step_id"),
        "current_action": state.get("current_action"),
        "decision_reason": state.get("decision_reason"),
        "geometry_id": state.get("geometry_id"),
        "checked_geometry_id": state.get("checked_geometry_id"),
        "placed_buildings": state.get("placed_buildings", []),
        "remaining_candidate_positions": state.get("remaining_candidate_positions", []),
        "requested_positions": state.get("requested_positions", []),
        "requested_position_assessment": state.get("requested_position_assessment", {}),
        "target_building_count": state.get("target_building_count", 1),
        "optimization_cycles": state.get("optimization_cycles"),
        "max_optimization_cycles": state.get("max_optimization_cycles"),
        "replan_required": state.get("replan_required"),
        "replan_reason": state.get("replan_reason"),
        "site_context": state.get("site_context", {}),
        "site_boundary": state.get("site_boundary", []),
        "building_intents": state.get("building_intents", []),
        "shape_context": state.get("shape_context", {}),
        "violations": state.get("violations", []),
        "constraint_results": state.get("constraint_results", {}),
        "evaluation_results": state.get("evaluation_results", {}),
        "human_request": state.get("human_request"),
        "error": state.get("error"),
    }


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content)


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = _strip_code_fence(text)
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM response must be a JSON object")
    return parsed


def _format_building_label(index: int) -> str:
    return f"building {index}"


def _repair_generate_shape_decision(
    decision: RoutingDecision,
    state: dict[str, Any],
    catalog: ToolCatalog,
    active_step: PlanStep,
) -> RoutingDecision:
    if active_step.action != "generate_shape":
        return decision

    available_names = set(catalog.names_for_action("generate_shape"))
    if "generate_building_boundary" not in available_names:
        return decision

    defaults = get_boundary_planning_defaults()
    tool_defaults = dict(defaults["tool_argument_defaults"])
    user_prompt = str(state.get("user_prompt", ""))
    site_area_sqm = _extract_site_area_sqm(state)
    explicit_building_area_sqm = _extract_explicit_building_area_sqm(user_prompt)
    inferred_building_type = _infer_requested_building_type(user_prompt)
    requested_rotation = _extract_requested_rotation(user_prompt)
    has_explicit_building_area = _mentions_explicit_building_area(user_prompt)
    fallback_arguments = {
        "area": explicit_building_area_sqm or _default_boundary_area(site_area_sqm, defaults["default_site_coverage_ratio"]),
        "building_type": inferred_building_type or tool_defaults["building_type"],
        "building_depth": tool_defaults["building_depth"],
        "shape_ratio": tool_defaults["shape_ratio"],
        "location_xy": tool_defaults["location_xy"],
        "is_mirrored": tool_defaults["is_mirrored"],
        "max_rotation_angle": tool_defaults["max_rotation_angle"],
        "max_rotation_step": tool_defaults["max_rotation_step"],
        "rotation_step": tool_defaults["rotation_step"],
    }
    if requested_rotation is not None:
        fallback_arguments.update(_rotation_arguments_for_requested_angle(requested_rotation))

    patched_calls: list[ToolCall] = []
    for tool_call in decision.tool_calls:
        if tool_call.name not in available_names:
            continue
        if tool_call.name != "generate_building_boundary":
            patched_calls.append(tool_call)
            continue
        arguments = dict(tool_call.arguments)
        if inferred_building_type is not None:
            arguments["building_type"] = inferred_building_type
        if not has_explicit_building_area:
            arguments["area"] = fallback_arguments["area"]
        if requested_rotation is not None:
            arguments.update(_rotation_arguments_for_requested_angle(requested_rotation))
        for key, value in fallback_arguments.items():
            if arguments.get(key) is None:
                arguments[key] = value
        patched_calls.append(ToolCall(name=tool_call.name, arguments=arguments))

    if any(tool_call.name == "generate_building_boundary" for tool_call in patched_calls):
        return RoutingDecision(
            action=decision.action,
            reasoning=decision.reasoning,
            tool_calls=tuple(patched_calls),
            user_question=decision.user_question,
        )

    return RoutingDecision(
        action="generate_shape",
        reasoning=(decision.reasoning or active_step.goal),
        tool_calls=(ToolCall(name="generate_building_boundary", arguments=fallback_arguments),),
        user_question=decision.user_question,
    )


def _extract_site_area_sqm(state: dict[str, Any]) -> float | None:
    site_context = state.get("site_context", {})
    if isinstance(site_context, dict):
        found = _find_numeric_value(site_context, "site_area_sqm")
        if found is not None:
            return found
    user_prompt = str(state.get("user_prompt", ""))
    match = re.search(r"site area of\s*(\d+(?:\.\d+)?)", user_prompt, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _find_numeric_value(payload: Any, key: str) -> float | None:
    if isinstance(payload, dict):
        if key in payload and isinstance(payload[key], (int, float)):
            return float(payload[key])
        for value in payload.values():
            found = _find_numeric_value(value, key)
            if found is not None:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_numeric_value(item, key)
            if found is not None:
                return found
    return None


def _default_boundary_area(site_area_sqm: float | None, default_site_coverage_ratio: float) -> float:
    if site_area_sqm is None or site_area_sqm <= 0:
        return 1000.0
    return round(site_area_sqm * default_site_coverage_ratio, 2)


def _infer_requested_building_type(user_prompt: str) -> str | None:
    prompt_lower = user_prompt.lower()
    if "l-shaped" in prompt_lower or "l shaped" in prompt_lower:
        return "L"
    if "t-shaped" in prompt_lower or "t shaped" in prompt_lower:
        return "T"
    if "i-shaped" in prompt_lower or "i shaped" in prompt_lower or "bar building" in prompt_lower:
        return "I"
    return None


def _mentions_explicit_building_area(user_prompt: str) -> bool:
    prompt_lower = user_prompt.lower()
    return any(
        phrase in prompt_lower
        for phrase in ("building area", "footprint area", "requested area", "target area", "gfa")
    )


def _extract_explicit_building_area_sqm(user_prompt: str) -> float | None:
    prompt_lower = user_prompt.lower()
    patterns = (
        r"building area of\s*(\d+(?:\.\d+)?)",
        r"building area\s*(?:=|is)?\s*(\d+(?:\.\d+)?)",
        r"footprint area of\s*(\d+(?:\.\d+)?)",
        r"footprint area\s*(?:=|is)?\s*(\d+(?:\.\d+)?)",
        r"gfa of\s*(\d+(?:\.\d+)?)",
        r"gfa\s*(?:=|is)?\s*(\d+(?:\.\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, prompt_lower, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _extract_requested_rotation(user_prompt: str) -> float | None:
    prompt_lower = user_prompt.lower()
    patterns = (
        r"rotate(?: the)? building by\s*(\d+(?:\.\d+)?)\s*degrees?",
        r"rotate(?: the)? footprint by\s*(\d+(?:\.\d+)?)\s*degrees?",
        r"rotated by\s*(\d+(?:\.\d+)?)\s*degrees?",
    )
    for pattern in patterns:
        match = re.search(pattern, prompt_lower, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _rotation_arguments_for_requested_angle(requested_rotation: float) -> dict[str, float | int]:
    if requested_rotation <= 0:
        return {
            "max_rotation_angle": 0.0,
            "max_rotation_step": 0,
            "rotation_step": 0,
        }
    return {
        "max_rotation_angle": requested_rotation,
        "max_rotation_step": 1,
        "rotation_step": 1,
    }