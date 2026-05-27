"""
SUGGESTION_CRITIC node — reviews each suggestion for feasibility, persona priority
alignment, and cross-sense unintended consequences before RESPOND presents them.
Writes suggestion_critique to state.
"""

from __future__ import annotations
import json
from _runtime.llm import call_llm_simple


_SYSTEM_PROMPT = """\
You are a senior architectural comfort critic.

You receive a list of generated suggestions for improving sensory comfort,
the root causes of the conflicts, and the persona profile.

Your ONLY job: critically review each suggestion for:
  1. Feasibility — is this actually doable in this room given its size and type?
  2. Persona priority — does it address the most important sense for this person first?
  3. Cross-sense consequences — does this fix one thing but worsen another?
     (e.g. heavy curtains fix glare → reduce daylight → reduce visual comfort score)

Output format:
  [Room Name]
  - [suggestion]: FEASIBLE | QUESTIONABLE | INFEASIBLE — [one sentence reason]
    [if cross-sense risk: "WARNING: may affect [sense] — [brief explanation]"]

Rules:
  - Be direct and specific. No padding.
  - If a suggestion is clearly good, just mark FEASIBLE and move on.
  - Focus your critique on QUESTIONABLE or INFEASIBLE cases.
  - If suggestions are ranked correctly for this persona, say so briefly.
  - Plain text. No markdown. No JSON.

SUGGESTIONS:
{suggestions_summary}

CONFLICT ROOT CAUSES (context for feasibility):
{conflict_reasoning}

PERSONA PRIORITIES:
{persona_priorities}
"""


def _format_suggestions(suggestions_json: str) -> str:
    if not suggestions_json:
        return "(no suggestions)"
    try:
        data = json.loads(suggestions_json)
        improvements = data.get("improvements", [])
        if not improvements:
            return "no suggestions generated"
        lines = []
        for room in improvements:
            name = room.get("roomName", "?")
            for s in room.get("suggestions", []):
                sense = s.get("sense", "?")
                suggestion = s.get("suggestion", "")
                lines.append(f"{name} / {sense}: {suggestion}")
        return "\n".join(lines)
    except Exception:
        return suggestions_json


def _format_persona_priorities(persona_profile: dict) -> str:
    if not persona_profile:
        return "no specific priorities"
    primary = persona_profile.get("primary_user", {})
    priorities = primary.get("sensory_priorities", [])
    sensitivities = primary.get("sensory_sensitivities", [])
    parts = []
    if priorities:
        parts.append(f"Top senses: {', '.join(priorities)}")
    if sensitivities:
        parts.append(f"Sensitivities: {', '.join(sensitivities)}")
    secondary = persona_profile.get("secondary_user")
    if secondary:
        sec_p = secondary.get("sensory_priorities", [])
        if sec_p:
            parts.append(f"Second occupant top senses: {', '.join(sec_p)}")
    return "; ".join(parts) if parts else "no specific priorities"


def build_suggestion_critic_node(llm):
    """Return the suggestion_critic node function, capturing the LLM instance."""

    def suggestion_critic_node(state: dict) -> dict:
        suggestions_json: str = state.get("last_suggestions_json", "")
        conflict_reasoning: str = state.get("conflict_reasoning", "")
        persona_profile: dict = state.get("persona_profile") or {}

        print("[suggestion_critic] Critiquing suggestions...")

        suggestions_summary = _format_suggestions(suggestions_json)
        persona_priorities = _format_persona_priorities(persona_profile)

        system = _SYSTEM_PROMPT.format(
            suggestions_summary=suggestions_summary,
            conflict_reasoning=conflict_reasoning or "(not available)",
            persona_priorities=persona_priorities,
        )

        critique = call_llm_simple(llm, system, "Critique these suggestions.")
        print(f"[suggestion_critic] Critique: {critique[:80]}...")

        return {
            **state,
            "suggestion_critique": critique,
        }

    return suggestion_critic_node
