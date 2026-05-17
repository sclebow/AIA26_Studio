from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_openai import ChatOpenAI

from .models import PlanStep, RoutingDecision
from .tool_catalog import ToolCatalog


SUPERVISOR_PROMPT = """
You are the execution supervisor for one active plan step in a site design LangGraph agent.

Active step:
{active_step}

Supervisor rules:
- Only act on the active step.
- If the active step is `generate_shape`, return `generate_shape` with one or more valid shape-generation tool calls.
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

        placed_buildings = list(state.get("placed_buildings", []))
        target_building_count = max(1, int(state.get("target_building_count", 1) or 1))
        current_building_index = len(placed_buildings) + 1
        requested_positions = list(state.get("requested_positions", []))
        active_requested_position = (
            requested_positions[current_building_index - 1]
            if 0 <= current_building_index - 1 < len(requested_positions)
            else None
        )
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
                goal="Create the next geometry candidate for the site.",
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
                goal="Check whether the user's requested position works for the current building.",
                status=(
                    "completed"
                    if requested_position_checked or not active_requested_position
                    else ("pending" if geometry_id else "skipped")
                ),
            ),
            PlanStep(
                step_id="check_constraints",
                action="check_constraints",
                goal="Validate the current geometry against all constraints.",
                status="completed" if current_geometry_checked else ("pending" if geometry_id else "skipped"),
            ),
            PlanStep(
                step_id="optimize",
                action="optimize",
                goal="Repair the highest-priority violations on the current geometry.",
                status="pending" if violations and not maxed_out else "skipped",
            ),
            PlanStep(
                step_id="evaluate",
                action="evaluate",
                goal="Evaluate the valid geometry for design quality and performance.",
                status=(
                    "completed"
                    if state.get("evaluation_results")
                    else ("pending" if current_geometry_checked and not violations else "skipped")
                ),
            ),
            PlanStep(
                step_id="place_building",
                action="place_building",
                goal="Place the current validated building into Rhino/Grasshopper.",
                status=(
                    "completed"
                    if current_geometry_already_placed
                    else ("pending" if can_place_current_building else "skipped")
                ),
            ),
            PlanStep(
                step_id="analyze_remaining_positions",
                action="analyze_remaining_positions",
                goal="Analyze the remaining site area for the next building candidate positions.",
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
        return RoutingDecision.from_payload(content)

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