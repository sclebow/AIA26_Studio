"""
SUGGEST node — calls generate_suggestions on conflicts from DETECT.
"""

from __future__ import annotations
from nodes._shared.utils import unwrap_mcp_result


def _persona_label(persona_profile: dict) -> str:
    if not persona_profile:
        return "Neutral"
    pt = persona_profile.get("persona_type", "")
    valid = {"Elderly 65+", "Child under 12", "Sensory Sensitive", "Young Active", "Neutral"}
    return pt if pt in valid else "Neutral"


def build_suggest_node(mcp_client):
    def suggest_node(state: dict) -> dict:
        conflicts_json  = state.get("last_conflicts_json", "")
        persona_profile = state.get("persona_profile") or {}
        persona_label   = _persona_label(persona_profile)

        if not conflicts_json:
            raise RuntimeError("[suggest] No conflicts available — DETECT must run first.")

        print(f"[suggest] generate_suggestions (persona={persona_label})")
        raw_output = mcp_client.call_tool(
            "generate_suggestions",
            {"conflicts": conflicts_json, "persona": persona_label},
        )
        suggestions_json = unwrap_mcp_result(raw_output)
        print(f"[suggest] Suggestions received ({len(suggestions_json)} chars)")

        return {**state, "last_suggestions_json": suggestions_json}

    return suggest_node
