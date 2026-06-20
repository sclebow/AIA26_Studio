"""
DETAIL_RESPOND node — answers specific follow-up questions about the current analysis.
Reached when action="follow_up": user is asking about existing results, not requesting
a new analysis run. Has full access to all cached data and specialist interpretations.
No length restriction — answers as thoroughly as the question requires.
"""

from __future__ import annotations
import json
from _runtime.llm import respond_text
from nodes._shared.utils import grounded_facts
from nodes._shared.register import register_tone
from nodes._shared.persona_context import format_persona_for_prompt


_SYSTEM_PROMPT = """\
You are Sensi, an architectural comfort analyst specialising in multi-sensory wellbeing:
thermal, visual, acoustic, spatial, olfactory, tactile.

The user just saw an analysis and is now asking a specific follow-up question.
You have full access to all analysis results below. Answer their question directly.

Rules:
  - Answer ONLY what was asked. Do not re-summarise the whole analysis.
  - Use ONLY the data provided. Never invent scores, room names, or suggestions.
  - Name rooms by their EXACT name and senses by their exact word (thermal/visual/acoustic/
    spatial/olfactory/tactile) - the live canvas highlights whatever you name, so don't paraphrase.
  - NEVER claim a room or sense is the "lowest/highest/worst/best of all rooms" or
    "lower than other rooms" unless that exact ranking is in GROUNDED FACTS below.
    Describe the room's own values without ranking them against others otherwise.
  - Length: as long as the answer needs — not capped at 2-3 sentences.
  - If the user asks "why", use the conflict root-cause reasoning below.
  - If the user asks "what should I do", use the suggestion critique below.
  - If no analysis data is available yet, say so and offer to run one.
  - No markdown. No JSON. Plain language only.

VOICE for a {user_type}: {register_tone}

USER TYPE: {user_type}
PERSONA: {persona_summary}
LAYOUT ID: {layout_id}
"""


def _safe_format(json_str: str, label: str) -> str:
    if not json_str or not json_str.strip():
        return f"({label}: not yet run)"
    try:
        return json.dumps(json.loads(json_str), indent=2)
    except Exception:
        return json_str


def build_detail_respond_node(llm):
    """Return the detail_respond node function, capturing the LLM instance."""

    def detail_respond_node(state: dict) -> dict:
        raw_prompt: str      = state.get("raw_prompt", "")
        user_type: str       = state.get("user_type", "architect")
        layout_id            = state.get("layout_id") or "?"
        persona_profile: dict = state.get("persona_profile") or {}

        persona_summary = format_persona_for_prompt(persona_profile)

        system = _SYSTEM_PROMPT.format(
            user_type=user_type,
            register_tone=register_tone(user_type),
            persona_summary=persona_summary,
            layout_id=layout_id,
        )

        sections = [
            "User question: " + raw_prompt,
            "",
            grounded_facts(state.get("last_scores_json", "")) or "GROUNDED FACTS: (none available)",
            "",
            "--- SCORES ---",
            _safe_format(state.get("last_scores_json", ""), "scores"),
            "",
            "--- CONFLICTS ---",
            _safe_format(state.get("last_conflicts_json", ""), "conflicts"),
            "",
            "--- SUGGESTIONS ---",
            _safe_format(state.get("last_suggestions_json", ""), "suggestions"),
        ]

        if state.get("score_interpretation", "").strip():
            sections += [
                "",
                "--- SCORE INTERPRETATION (why scores matter for this persona) ---",
                state["score_interpretation"],
            ]
        if state.get("conflict_reasoning", "").strip():
            sections += [
                "",
                "--- CONFLICT ROOT CAUSES (why each sense failed) ---",
                state["conflict_reasoning"],
            ]
        if state.get("suggestion_critique", "").strip():
            sections += [
                "",
                "--- SUGGESTION CRITIQUE (feasibility + cross-sense warnings) ---",
                state["suggestion_critique"],
            ]

        user_message = "\n".join(sections)

        print("[detail_respond] Answering specific follow-up question...")
        response = respond_text(llm, system, user_message)
        print(f"[detail_respond] Response: {response[:80]}...")

        return {**state, "final_response": response}

    return detail_respond_node
