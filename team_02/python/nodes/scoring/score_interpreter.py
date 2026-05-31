"""
SCORE_INTERPRETER node — translates comfort scores into lived human experience.
Focuses on scores that are notably high (>0.75) or low (<0.50) for this persona.
Output feeds CONFLICT_REASONER and RESPOND.
"""

from __future__ import annotations
import json
from _runtime.llm import call_llm_simple
from nodes._shared.utils import grounded_facts


_SYSTEM_PROMPT = """\
You are a sensory comfort interpreter for an architectural analysis tool.

You receive comfort scores (0.0–1.0) per sense per room, and a persona profile
describing who lives in this space.

Your ONLY job: explain what these scores MEAN for THIS specific person.
Do NOT describe the scores themselves — describe the LIVED EXPERIENCE.

Rules:
  - Reference the persona by their actual traits (age, sensory sensitivities, use patterns)
  - Focus on scores that are notably high (>0.75) or notably low (<0.50)
  - One short sentence per room × sense combination that matters
  - Skip rooms or senses that are unremarkable for this persona
  - Do NOT suggest fixes. Do NOT mention conflicts. Just interpret meaning.
  - Plain language. No jargon. No markdown. No JSON.
  - NEVER state that a score is the "lowest/highest/worst/best of all rooms" or
    "across the layout" unless that exact ranking appears in GROUNDED FACTS below.
    Every number you cite must be copied exactly from SCORES. Do not compute or
    invent comparisons.

Format:
  [Room Name]
  - [sense]: [what this score means for this persona in one sentence]
  (repeat for notable senses only)

PERSONA:
{persona_summary}

{grounded}

SCORES:
{scores_summary}
"""


def _format_scores(scores_json: str) -> str:
    if not scores_json:
        return "(no scores)"
    try:
        data = json.loads(scores_json)
        lines = []
        for room in data.get("rooms", []):
            name = room.get("roomName", "?")
            sc = room.get("comfortScores", {})
            overall = room.get("overallScore", 0.0)
            lines.append(f"{name} (overall: {overall:.2f})")
            for sense, val in sc.items():
                lines.append(f"  {sense}: {val:.2f}")
        return "\n".join(lines)
    except Exception:
        return scores_json


def _format_persona(persona_profile: dict) -> str:
    """Summarise the flat persona_compiler v2 profile for the interpreter prompt."""
    if not persona_profile:
        return "neutral adult, no specific sensory sensitivities"
    try:
        parts = []
        name = persona_profile.get("name", "")
        role = persona_profile.get("role", "")
        desc = persona_profile.get("description", "")
        if desc:
            parts.append(desc)
        elif name and role:
            parts.append(f"{name}, {role}")
        if persona_profile.get("age_group"):
            parts.append(f"age group: {persona_profile['age_group']}")
        if persona_profile.get("household_type"):
            parts.append(f"household: {persona_profile['household_type']}")
        if persona_profile.get("sensory_priorities"):
            parts.append(f"sensory priorities: {', '.join(persona_profile['sensory_priorities'])}")
        if persona_profile.get("sensory_sensitivities"):
            parts.append(f"sensitivities: {', '.join(persona_profile['sensory_sensitivities'])}")
        if persona_profile.get("key_requirements"):
            parts.append(f"non-negotiables: {'; '.join(persona_profile['key_requirements'])}")
        return "; ".join(parts) if parts else "no profile"
    except Exception:
        return str(persona_profile)


def build_score_interpreter_node(llm):
    """Return the score_interpreter node function, capturing the LLM instance."""

    def score_interpreter_node(state: dict) -> dict:
        scores_json: str      = state.get("last_scores_json", "")
        persona_profile: dict = state.get("persona_profile") or {}

        print("[score_interpreter] Interpreting scores for persona...")

        scores_summary  = _format_scores(scores_json)
        persona_summary = _format_persona(persona_profile)
        grounded        = grounded_facts(scores_json) or "GROUNDED FACTS: (none available)"

        system = _SYSTEM_PROMPT.format(
            persona_summary=persona_summary,
            grounded=grounded,
            scores_summary=scores_summary,
        )

        interpretation = call_llm_simple(llm, system, "Interpret these scores.")
        print(f"[score_interpreter] Interpretation: {interpretation[:80]}...")

        return {
            **state,
            "score_interpretation": interpretation,
        }

    return score_interpreter_node
