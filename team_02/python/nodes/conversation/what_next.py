"""
WHAT_NEXT node — offers 2-3 contextual next steps after every complete turn.
Adapts suggestions to what just ran (analyze/detect/full/overview/chitchat)
and to user_type. Appends to chitchat responses rather than replacing them.
"""

from __future__ import annotations
import json
from _runtime.llm import call_llm_simple


def _extract_worst_finding(scores_json: str) -> str:
    """Return a one-phrase description of the single worst room×sense."""
    if not scores_json:
        return "none yet"
    try:
        data = json.loads(scores_json)
        worst_val = 1.0
        worst_desc = "none"
        for room in data.get("rooms", []):
            name = room.get("roomName", "?")
            for sense, val in room.get("comfortScores", {}).items():
                if val < worst_val:
                    worst_val = val
                    worst_desc = f"{sense} in {name} ({val:.2f})"
        return worst_desc
    except Exception:
        return "none"


def _format_persona(persona_profile: dict) -> str:
    if not persona_profile:
        return "no specific persona"
    # Flat schema (persona_compiler v2)
    if "name" in persona_profile or "role" in persona_profile:
        desc = persona_profile.get("description", "")
        name = persona_profile.get("name", "")
        role = persona_profile.get("role", "")
        return desc or (f"{name}, {role}" if name else role or "no profile")
    # Legacy nested schema
    primary = persona_profile.get("primary_user", {})
    return primary.get("description", "no specific persona")


_SYSTEM_PROMPT = """\
You are Sensi. The user has just seen a result. Offer the most useful next step — specific to
what was found, not generic.

What just ran and what to suggest:
  analyze    → The panel shows scores. Suggest: "detect the conflicts" or "ask me why [worst sense] is low"
               or "run the full analysis for suggestions".
  detect     → Conflicts are visible. Suggest: "get improvement suggestions" or
               "ask me why [conflict room] is failing" or "run a what-if scenario".
  full       → Scores + conflicts + suggestions are all visible. Suggest: "try a what-if"
               (what if I change a material?), "compare this to another persona", or a specific question.
  follow_up  → Just answered a specific question. Suggest: continuing to dig, running a what-if,
               or exploring the panel section that answers the next logical question.
  overview   → Room list was shown. Suggest running a comfort analysis.
  chitchat   → Nothing analysed yet. Offer to start.

Register by user_type:
  architect  → concise, technical: "Want to run a what-if on the glazing?"
  client     → warm, plain: "Want me to suggest ways to fix the bedroom?"
  learner    → educational: "A good next step would be checking for conflicts — want to try?"

Rules:
  - Maximum 2 sentences. Be specific — name the room or sense if you know it.
  - Do NOT summarise what just happened. They just read it.
  - Do NOT list options with bullet points. Write it as natural speech.
  - Plain text only. No markdown.
  - End with one short alternative: "or just ask me anything about the results."

CONTEXT:
  user_type:   {user_type}
  last_path:   {last_path}
  layout_id:   {layout_id}
  persona:     {persona_summary}
  worst_finding: {worst_finding}
"""


def build_what_next_node(llm):
    """Return the what_next node function, capturing the LLM instance."""

    def what_next_node(state: dict) -> dict:
        user_type: str     = state.get("user_type", "architect")
        comfort_depth: str = state.get("comfort_depth", "analyze")
        intent: str        = state.get("intent", "comfort")
        layout_id: str     = state.get("layout_id") or "?"
        persona_profile: dict = state.get("persona_profile") or {}

        # Determine what just happened
        if intent == "overview":
            last_path = "overview (room list, no analysis)"
        elif intent in ("comfort", "tools"):
            last_path = f"comfort analysis — depth: {comfort_depth}"
        elif intent == "chitchat":
            last_path = "chitchat conversation"
        elif intent == "inspire":
            last_path = "inspire (atmosphere)"
        elif intent == "follow_up":
            last_path = f"follow_up (specific question about {comfort_depth} results)"
        else:
            last_path = intent

        persona_summary = _format_persona(persona_profile)
        worst_finding   = _extract_worst_finding(state.get("last_scores_json", ""))

        print("[what_next] Generating next step offer...")

        system = _SYSTEM_PROMPT.format(
            user_type=user_type,
            last_path=last_path,
            layout_id=layout_id,
            persona_summary=persona_summary,
            worst_finding=worst_finding,
        )

        offer = call_llm_simple(llm, system, "Offer next steps.")

        # Always append the next-step nudge to the existing response.
        # For comfort/tools paths the respond node already wrote the full
        # analysis into final_response — we must not overwrite it.
        existing = state.get("final_response", "")
        if existing:
            combined = existing + "\n\n" + offer
        else:
            combined = offer

        return {
            **state,
            "final_response": combined,
        }

    return what_next_node
