from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Protocol

try:
    from langchain_openai import ChatOpenAI
except ModuleNotFoundError:  # pragma: no cover - exercised when LLM deps are absent in unit tests
    ChatOpenAI = Any  # type: ignore[misc,assignment]

from .llm import resolve_active_llm
from .models import DesignBrief, PlanStep, RoutingDecision
from .models import ToolCall
from .tools.generate_building_boundary import get_boundary_planning_defaults
from .tool_catalog import ToolCatalog


SUPERVISOR_PROMPT = """
You execute the one active plan step of a site-design agent. Choose tool calls
that serve the design brief; the runtime fills in missing arguments and enforces
step/tool policy, so focus on intent, not bookkeeping. Use `await_human` only when
the step truly cannot proceed without clarification.

Active step:
{active_step}

Design brief (the user's intent — let it guide shape, area, and emphasis):
{design_brief}

Self-debug directive (a previous attempt failed validation; if non-empty, follow
this correction when choosing this step's tool arguments):
{debug_directive}

Return JSON only:
{{
  "action": "{action}",
  "reasoning": "short explanation",
  "user_question": "only for await_human, else empty string",
  "tool_calls": [{{"name": "tool_name", "arguments": {{}}}}]
}}

Relevant tools:
{tool_catalog}

State snapshot:
{state_snapshot}
"""


BRIEF_PROMPT = """
You extract a structured design brief from a user's site-design request.
Return JSON only, matching this schema (use null for anything you cannot infer —
never invent values):
{{
  "building_count": <int, default 1>,
  "buildings": [
    {{
      "shape_preference": "I|L|T|U|H|Y|X|O|auto",
      "footprint_area_sqm": <number or null>,
      "storeys": <int or null>,
      "use": "residential|office|mixed",
      "intent_text": "<short per-building intent, else empty>"
    }}
  ],
  "courtyard_requested": <bool>,
  "courtyard_qualities": ["quiet"|"sunny"|"private"|...],
  "parking_requested": <bool>,
  "requested_rotation_deg": <number or null>,
  "view_weight": <0..1>, "sun_weight": <0..1>, "alignment_weight": <0..1>,
  "ambiguities": ["<anything vague, contradictory, or missing>"]
}}
Rules:
- One entry in "buildings" per building; length should match building_count when known.
- Raise objective weights for whatever the user emphasizes (e.g. "daylight matters most" -> higher sun_weight). Default each weight to 0.5.
- Put genuine gaps and contradictions in "ambiguities" instead of guessing.

User request:
{user_prompt}
"""


JUDGE_PROMPT = """
You are the design judge in a site-planning agent's self-validation loop. The
hard geometric checks (valid polygon, fits the site, no overlap, area tolerance)
already PASSED. Your job is the softer question: does this footprint actually
satisfy the user's design brief (requested shape family, use, emphasis)?

Be decisive but fair — only fail when there is a clear, nameable mismatch with
the brief, not for stylistic nitpicks. Return JSON only:
{{
  "satisfies_brief": <bool>,
  "score": <0..1>,
  "reasons": ["<short, concrete reason>", ...]
}}

Design brief:
{design_brief}

Validation metrics (from the deterministic checker):
{validation_metrics}

Current geometry summary:
{geometry_summary}
"""


DEBUG_PROMPT = """
You are the self-debug step of a site-planning agent. The last building footprint
FAILED validation. Diagnose the most likely cause from the failures and produce a
single, concrete corrective directive for the next regeneration attempt. Be
specific about WHAT to change (area, shape family, depth/ratio, location, rotation)
and in WHICH direction — the generator will read your directive verbatim.

Do not repeat a directive that already failed (see prior attempts). Return JSON only:
{{
  "diagnosis": "<one sentence: why it failed>",
  "directive": "<imperative instruction for the next generate_building_boundary call>"
}}

Design brief:
{design_brief}

Validation result (failures + metrics):
{validation_result}

Prior debug attempts (most recent last):
{debug_history}

Geometry summary:
{geometry_summary}
"""


REPORT_PROMPT = """
You are writing the final report for a site design agent.
Summarize the chosen geometry, remaining constraint state, evaluation results, and next recommendation.
Keep it concise and concrete.
Mention the placement-fit loop summary when it is available.

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

    # Optional: engines may expose extract_brief for LLM intent comprehension.
    # The graph's extract_brief node detects it via getattr and falls back to the
    # deterministic regex extractor when it is absent, so stub engines used in
    # tests do not need to implement it.


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
        remaining_positions_analyzed = bool(placed_buildings) and state.get("remaining_positions_analyzed_for_count") == len(placed_buildings)
        more_buildings_needed = len(placed_buildings) < target_building_count
        current_geometry_already_placed = any(
            isinstance(item, dict) and item.get("geometry_id") == geometry_id
            for item in placed_buildings
        )

        # Self-validation + self-debug loop. ``validate`` produces a pass/fail
        # verdict for the *current* geometry; on failure ``debug`` reasons about
        # why and clears the geometry so generate_shape runs again — bounded by
        # ``max_debug_attempts`` so a hopeless candidate still reaches a report.
        validation_for_current = bool(
            geometry_id
            and state.get("validated_geometry_id") == geometry_id
            and state.get("validation_result")
        )
        validation_passed = validation_for_current and bool(state.get("validation_passed"))
        validation_failed = validation_for_current and not bool(state.get("validation_passed"))
        debug_attempts = int(state.get("debug_attempts", 0) or 0)
        max_debug_attempts = int(state.get("max_debug_attempts", 0) or 0)
        debug_exhausted = debug_attempts >= max_debug_attempts
        validation_dead_end = validation_failed and debug_exhausted

        can_place_current_building = bool(
            geometry_id
            and current_geometry_checked
            and not violations
            and validation_passed
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

        if workflow_mode == "masterplan":
            # Whole-site masterplanning: read the site, run the circulation-first
            # 17-step pipeline once, then report. No per-building generate/validate
            # loop — the masterplan tool places, scores and optimises the layout.
            masterplan_done = bool(state.get("masterplan_result"))
            return (
                PlanStep(
                    step_id="read_site",
                    action="read_site",
                    goal="Load site boundary, context, and legal constraints.",
                    status="completed" if state.get("site_context") else "pending",
                ),
                PlanStep(
                    step_id="generate_masterplan",
                    action="generate_masterplan",
                    goal="Generate, score and optimise a whole-site masterplan (circulation, fire, parking).",
                    status=(
                        "completed"
                        if masterplan_done
                        else ("pending" if state.get("site_context") else "skipped")
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
                    goal="Write the masterplan report for the generated layout.",
                    status=(
                        "completed"
                        if report_complete and not await_question
                        else ("pending" if masterplan_done or state.get("error") else "skipped")
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
                step_id="validate",
                action="validate",
                goal=f"Validate {current_building_label}: valid polygon, fits the site, no overlap, area in tolerance, and matches the brief.{intent_suffix}",
                status=(
                    "completed"
                    if validation_for_current
                    else (
                        "pending"
                        if geometry_id and current_geometry_checked and not violations
                        else "skipped"
                    )
                ),
            ),
            PlanStep(
                step_id="debug",
                action="debug",
                goal=f"Diagnose why {current_building_label} failed validation and adjust the next attempt.{intent_suffix}",
                status="pending" if validation_failed and not debug_exhausted else "skipped",
            ),
            PlanStep(
                step_id="evaluate",
                action="evaluate",
                goal=f"Evaluate {current_building_label} for design quality and performance.{intent_suffix}",
                status=(
                    "completed"
                    if state.get("evaluation_results")
                    else ("pending" if validation_passed else "skipped")
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
                    if remaining_positions_analyzed
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
                        if report_ready or maxed_out or validation_dead_end or state.get("error")
                        else "skipped"
                    )
                ),
            ),
        )


@dataclass
class OpenAIDecisionEngine:
    llm: ChatOpenAI
    decision_provider: str | None = None
    decision_model: str | None = None
    report_provider: str | None = None
    report_model: str | None = None

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
                action=active_step.action,
                design_brief=json.dumps(state.get("design_brief", {}), indent=2),
                debug_directive=str(state.get("debug_directive") or "").strip() or "(none)",
                tool_catalog=catalog.render_for_action(active_step.action),
                state_snapshot=json.dumps(snapshot, indent=2),
            ),
            user_prompt=state.get("user_prompt", ""),
        )
        decision = RoutingDecision.from_payload(content)
        return _repair_generate_shape_decision(decision, state, catalog, active_step)

    def extract_brief(
        self,
        user_prompt: str,
        layout_payload: dict[str, Any] | None = None,
    ) -> DesignBrief:
        """Comprehend the user's request into a typed :class:`DesignBrief`.

        On any LLM/parse failure this raises, and the caller (``resolve_brief``)
        falls back to the deterministic regex extractor.
        """
        del layout_payload  # The LLM reads the prompt directly; layout is a fallback concern.
        payload = self._invoke_json(
            system_prompt=BRIEF_PROMPT.format(user_prompt=user_prompt),
            user_prompt=user_prompt,
        )
        if isinstance(payload, dict):
            payload.setdefault("source", "llm")
        return DesignBrief.from_payload(payload)

    def judge_design(self, state: dict[str, Any]) -> dict[str, Any]:
        """LLM judge: does the (geometrically valid) footprint satisfy the brief?

        Only called once the deterministic checks pass. Returns
        ``{"satisfies_brief": bool, "score": float, "reasons": [...]}``. On any
        failure it raises and the validate node treats the brief check as a soft
        pass (the hard checks already guarantee a usable geometry).
        """
        payload = self._invoke_json(
            system_prompt=JUDGE_PROMPT.format(
                design_brief=json.dumps(state.get("design_brief", {}), indent=2),
                validation_metrics=json.dumps(
                    (state.get("validation_result") or {}).get("metrics", {}), indent=2
                ),
                geometry_summary=json.dumps(_geometry_summary(state), indent=2),
            ),
            user_prompt=state.get("user_prompt", ""),
        )
        return {
            "satisfies_brief": bool(payload.get("satisfies_brief", True)),
            "score": _clamp_unit(payload.get("score"), 0.5),
            "reasons": [str(r).strip() for r in payload.get("reasons", []) if str(r).strip()],
        }

    def propose_debug(self, state: dict[str, Any]) -> dict[str, str]:
        """LLM self-debug: turn validation failures into a corrective directive.

        Returns ``{"diagnosis": ..., "directive": ...}``. The directive is fed
        verbatim into the next supervisor call (see SUPERVISOR_PROMPT) so the
        regeneration changes in a *reasoned* direction rather than blindly.
        """
        payload = self._invoke_json(
            system_prompt=DEBUG_PROMPT.format(
                design_brief=json.dumps(state.get("design_brief", {}), indent=2),
                validation_result=json.dumps(state.get("validation_result", {}), indent=2),
                debug_history=json.dumps(state.get("debug_history", []), indent=2),
                geometry_summary=json.dumps(_geometry_summary(state), indent=2),
            ),
            user_prompt=state.get("user_prompt", ""),
        )
        return {
            "diagnosis": str(payload.get("diagnosis", "")).strip(),
            "directive": str(payload.get("directive", "")).strip(),
        }

    def build_report(self, state: dict[str, Any]) -> str:
        snapshot = _build_state_snapshot(state)
        messages = [
            {"role": "system", "content": REPORT_PROMPT.format(state_snapshot=json.dumps(snapshot, indent=2))},
            {"role": "user", "content": state.get("user_prompt", "")},
        ]
        active_llm = resolve_active_llm(
            self.llm,
            provider=self.report_provider,
            model=self.report_model,
        )
        result = active_llm.invoke(messages)
        return _normalize_content(result.content).strip()

    def _invoke_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        active_llm = resolve_active_llm(
            self.llm,
            provider=self.decision_provider,
            model=self.decision_model,
        )
        result = active_llm.invoke(messages)
        content = _normalize_content(result.content)
        return _parse_json_object(content)


def _summarize_site_model(site_model: Any) -> dict[str, Any]:
    """Compact view of the site model for prompts (full graph is too verbose)."""
    if not isinstance(site_model, dict) or not site_model.get("available"):
        return {"available": False}
    setbacks = site_model.get("setbacks") if isinstance(site_model.get("setbacks"), dict) else {}
    return {
        "available": True,
        "corner_count": len(site_model.get("corners", []) or []),
        "side_count": len(site_model.get("sides", []) or []),
        "site_area_sqm": setbacks.get("site_area_sqm"),
        "buildable_area_sqm": setbacks.get("buildable_area_sqm"),
        "has_roads": site_model.get("roads") is not None,
        "has_grid": site_model.get("grid") is not None,
        "has_sun": site_model.get("sun") is not None,
    }


def _build_state_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan": state.get("plan", []),
        "design_brief": state.get("design_brief", {}),
        "site_model_summary": _summarize_site_model(state.get("site_model", {})),
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
        "masterplan_result": state.get("masterplan_result", {}),
        "placement_fit_summary": state.get("placement_fit_summary", {}),
        "human_request": state.get("human_request"),
        "validation_passed": state.get("validation_passed"),
        "validation_result": state.get("validation_result", {}),
        "debug_attempts": state.get("debug_attempts"),
        "max_debug_attempts": state.get("max_debug_attempts"),
        "debug_directive": state.get("debug_directive"),
        "error": state.get("error"),
    }


def _geometry_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Compact description of the current footprint for judge/debug prompts."""
    shape_context = state.get("shape_context", {})
    payload: dict[str, Any] = {}
    if isinstance(shape_context, dict):
        for value in shape_context.values():
            if isinstance(value, dict):
                data = value.get("data", value)
                if isinstance(data, dict) and isinstance(data.get("boundary"), list):
                    payload = data
                    break
    metrics = (state.get("validation_result") or {}).get("metrics", {})
    boundary = payload.get("boundary") if isinstance(payload, dict) else None
    return {
        "geometry_id": state.get("geometry_id"),
        "shape_type": payload.get("shape_type") if isinstance(payload, dict) else None,
        "parameters": payload.get("parameters") if isinstance(payload, dict) else None,
        "boundary_point_count": len(boundary) if isinstance(boundary, list) else 0,
        "building_area_sqm": metrics.get("building_area_sqm") if isinstance(metrics, dict) else None,
        "target_area_sqm": metrics.get("target_area_sqm") if isinstance(metrics, dict) else None,
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
    site_boundary = _extract_site_boundary_from_state(state)
    preferred_location = _select_generation_location_hint(state)

    # Prefer the typed design brief for this building; fall back to prompt regex
    # so direct unit-test calls (which pass no brief) keep their existing behaviour.
    active_spec, brief_rotation = _active_brief_signals(state)

    spec_shape = active_spec.get("shape_preference")
    if isinstance(spec_shape, str) and spec_shape and spec_shape != "auto":
        inferred_building_type = spec_shape
    else:
        inferred_building_type = _infer_requested_building_type(user_prompt)

    spec_area = active_spec.get("footprint_area_sqm")
    if isinstance(spec_area, (int, float)):
        explicit_building_area_sqm = float(spec_area)
        has_explicit_building_area = True
    else:
        explicit_building_area_sqm = _extract_explicit_building_area_sqm(user_prompt)
        has_explicit_building_area = _mentions_explicit_building_area(user_prompt)

    requested_rotation = (
        brief_rotation if brief_rotation is not None else _extract_requested_rotation(user_prompt)
    )
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
        "optimize_placement": tool_defaults["optimize_placement"],
        "placement_clearance": tool_defaults["placement_clearance"],
        "population_size": tool_defaults["population_size"],
        "generation_count": tool_defaults["generation_count"],
        "random_seed": tool_defaults["random_seed"],
    }
    if preferred_location is not None:
        fallback_arguments["location_xy"] = preferred_location
    if site_boundary:
        fallback_arguments["site_boundary"] = site_boundary
        fallback_arguments["optimize_placement"] = True
    if requested_rotation is not None:
        fallback_arguments.update(_rotation_arguments_for_requested_angle(requested_rotation))

    # On a self-debug retry, perturb the random seed so the generator actually
    # explores a different candidate instead of reproducing the rejected one.
    debug_attempts = int(state.get("debug_attempts", 0) or 0)
    if debug_attempts > 0:
        base_seed = fallback_arguments.get("random_seed")
        base_seed = int(base_seed) if isinstance(base_seed, (int, float)) else 0
        fallback_arguments["random_seed"] = base_seed + debug_attempts * 1009

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
        if debug_attempts > 0:
            arguments["random_seed"] = fallback_arguments["random_seed"]
        if requested_rotation is not None:
            arguments.update(_rotation_arguments_for_requested_angle(requested_rotation))
        if preferred_location is not None and _uses_default_location(arguments.get("location_xy")):
            arguments["location_xy"] = preferred_location
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


def _active_brief_signals(state: dict[str, Any]) -> tuple[dict[str, Any], float | None]:
    """Return (active building spec, brief rotation) for the current building.

    Falls back to an empty spec and ``None`` rotation when no brief is present, so
    callers transparently revert to prompt-regex parsing.
    """
    brief = state.get("design_brief")
    if not isinstance(brief, dict) or not brief:
        return {}, None

    placed = state.get("placed_buildings", [])
    index = len(placed) if isinstance(placed, list) else 0
    buildings = brief.get("buildings", [])
    spec: dict[str, Any] = {}
    if isinstance(buildings, list) and 0 <= index < len(buildings) and isinstance(buildings[index], dict):
        spec = buildings[index]

    rotation = brief.get("requested_rotation_deg")
    rotation_value = float(rotation) if isinstance(rotation, (int, float)) else None
    return spec, rotation_value


def _select_generation_location_hint(state: dict[str, Any]) -> list[float] | None:
    placed_buildings = list(state.get("placed_buildings", []))
    if not placed_buildings:
        return None

    current_building_index = len(placed_buildings) + 1
    requested_positions = list(state.get("requested_positions", []))
    requested_xy = (
        _coerce_xy(requested_positions[current_building_index - 1])
        if 0 <= current_building_index - 1 < len(requested_positions)
        else None
    )
    candidate_positions = [
        xy
        for xy in (_coerce_xy(point) for point in state.get("remaining_candidate_positions", []))
        if xy is not None
    ]
    if not candidate_positions:
        return None

    if requested_xy is not None:
        best_candidate = min(
            candidate_positions,
            key=lambda point: math.dist(point, requested_xy),
        )
        return [best_candidate[0], best_candidate[1]]

    occupied_centroids = [
        centroid
        for centroid in (_boundary_centroid(item.get("boundary")) for item in placed_buildings if isinstance(item, dict))
        if centroid is not None
    ]
    if not occupied_centroids:
        first_candidate = candidate_positions[0]
        return [first_candidate[0], first_candidate[1]]

    best_candidate = max(
        candidate_positions,
        key=lambda point: min(math.dist(point, centroid) for centroid in occupied_centroids),
    )
    return [best_candidate[0], best_candidate[1]]


def _coerce_xy(point: Any) -> tuple[float, float] | None:
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return None
    if not all(isinstance(value, (int, float)) for value in point[:2]):
        return None
    return (float(point[0]), float(point[1]))


def _boundary_centroid(boundary: Any) -> tuple[float, float] | None:
    if not isinstance(boundary, list) or len(boundary) < 3:
        return None
    xy_points = [_coerce_xy(point) for point in boundary]
    xy_points = [point for point in xy_points if point is not None]
    if len(xy_points) < 3:
        return None
    if len(xy_points) > 1 and xy_points[0] == xy_points[-1]:
        xy_points = xy_points[:-1]
    if not xy_points:
        return None
    return (
        sum(point[0] for point in xy_points) / len(xy_points),
        sum(point[1] for point in xy_points) / len(xy_points),
    )


def _uses_default_location(location_xy: Any) -> bool:
    coerced = _coerce_xy(location_xy)
    if coerced is None:
        return True
    return math.isclose(coerced[0], 0.0, abs_tol=1e-9) and math.isclose(coerced[1], 0.0, abs_tol=1e-9)


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


def _extract_site_boundary_from_state(state: dict[str, Any]) -> list[list[float]] | None:
    site_boundary = state.get("site_boundary")
    if isinstance(site_boundary, list) and site_boundary:
        return site_boundary

    site_context = state.get("site_context", {})
    found = _find_list_value(site_context, "site_boundary")
    if found:
        return found

    layout_json = state.get("layout_json")
    if isinstance(layout_json, str) and layout_json.strip():
        try:
            layout_payload = json.loads(layout_json)
        except json.JSONDecodeError:
            return None
        boundary = layout_payload.get("site_boundary") if isinstance(layout_payload, dict) else None
        if isinstance(boundary, list) and boundary:
            return boundary
    return None


def _find_list_value(payload: Any, key: str) -> list[list[float]] | None:
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return value
        for item in payload.values():
            found = _find_list_value(item, key)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_list_value(item, key)
            if found:
                return found
    return None


def _infer_requested_building_type(user_prompt: str) -> str | None:
    prompt_lower = user_prompt.lower()
    if "y-shaped" in prompt_lower or "y shaped" in prompt_lower:
        return "Y"
    if "h-shaped" in prompt_lower or "h shaped" in prompt_lower:
        return "H"
    if "u-shaped" in prompt_lower or "u shaped" in prompt_lower or "courtyard building" in prompt_lower:
        return "U"
    if "x-shaped" in prompt_lower or "x shaped" in prompt_lower:
        return "X"
    if "o-shaped" in prompt_lower or "o shaped" in prompt_lower or "ring building" in prompt_lower:
        return "O"
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
        r"orient(?: the)? building to\s*(\d+(?:\.\d+)?)\s*degrees?",
        r"orientation(?: of the)? building\s*(?:=|is|to)?\s*(\d+(?:\.\d+)?)\s*degrees?",
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