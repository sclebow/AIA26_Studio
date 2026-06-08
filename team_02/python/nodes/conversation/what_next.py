"""
WHAT_NEXT node — offers a contextual next step after every complete turn.
Updated v4: uses `action` field (replaces dead `intent in ("comfort","tools")` + `comfort_depth`).
"""

from __future__ import annotations
import json
from _runtime.llm import call_llm_simple
from nodes._shared.register import register_tone


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
    desc = persona_profile.get("description", "")
    name = persona_profile.get("name", "")
    role = persona_profile.get("role", "")
    return desc or (f"{name}, {role}" if name else role or "no profile")


_SYSTEM_PROMPT = """\
You are Sensi. The user has just seen a result. Offer the most useful next step — specific to
what was found, not generic.

What just ran and what to suggest:
  analyze         → Panel shows scores. Suggest: "detect the conflicts" or "ask me why [worst sense] is low"
                    or "run the full analysis for suggestions".
  detect          → Conflicts visible. Suggest: "get improvement suggestions" or
                    "ask me why [conflict room] is failing" or "run a what-if scenario".
  full            → Scores + conflicts + suggestions all visible. Suggest: a change to fix the
                    weakest spot, "compare to another persona", or opening The Vision to see it rendered.
  follow_up       → Answered a specific question. Suggest continuing to dig or making a change.
  overview        → Room list shown. Suggest running a comfort analysis.
  chitchat        → Nothing analysed yet. Offer to start.
  edit            → One or more changes were applied and re-scored. Suggest the user COMMIT this as a
                    checkpoint to keep it, detect/full to see the impact, or another change. (Edits live
                    on a working draft until committed; The Vision shows the last committed checkpoint.)
  topologic       → Room connectivity shown. Suggest running comfort analysis next.
  biophilic       → Biophilic richness shown. Suggest adding plants or running detect.
  compare         → Two persona scores compared. Suggest picking the most relevant and running full.

Voice for a {user_type}: {register_tone}

Rules:
  - Maximum 2 sentences. Be specific — name the room or sense if you know it.
  - Do NOT summarise what just happened. They just read it.
  - Do NOT list options with bullet points. Write it as natural speech.
  - Plain text only. No markdown.
  - End with one short alternative: "or just ask me anything about the results."

CONTEXT:
  user_type:     {user_type}
  last_path:     {last_path}
  layout_id:     {layout_id}
  persona:       {persona_summary}
  worst_finding: {worst_finding}
"""


def build_what_next_node(llm):
    """Return the what_next node function, capturing the LLM instance."""

    def what_next_node(state: dict) -> dict:
        user_type: str        = state.get("user_type", "architect")
        action: str           = state.get("action", "")
        layout_id: str        = state.get("layout_id") or "?"
        persona_profile: dict = state.get("persona_profile") or {}

        # Map action → human-readable last_path for the LLM prompt
        _insight_actions = {"topologic", "biophilic", "compare"}
        _analysis_actions = {"analyze", "detect", "full"}

        if action == "overview":
            last_path = "overview (room list, no analysis)"
        elif action in _analysis_actions:
            last_path = f"comfort analysis — depth: {action}"
        elif action == "edit":
            last_path = "layout edit (one or more changes applied, re-scored)"
        elif action in _insight_actions:
            last_path = f"insight analysis — {action}"
        elif action == "chitchat":
            last_path = "chitchat conversation"
        elif action == "inspire":
            last_path = "inspire (atmosphere)"
        elif action == "follow_up":
            last_path = "follow_up (specific question about prior results)"
        else:
            last_path = action or "unknown"

        persona_summary = _format_persona(persona_profile)
        worst_finding   = _extract_worst_finding(state.get("last_scores_json", ""))

        print(f"[what_next] action={action} → last_path='{last_path}' | Generating next step offer...")

        system = _SYSTEM_PROMPT.format(
            user_type=user_type,
            register_tone=register_tone(user_type),
            last_path=last_path,
            layout_id=layout_id,
            persona_summary=persona_summary,
            worst_finding=worst_finding,
        )

        offer = call_llm_simple(llm, system, "Offer next steps.")

        existing = state.get("final_response", "")
        combined = (existing + "\n\n" + offer) if existing else offer

        return {**state, "final_response": combined}

    return what_next_node
