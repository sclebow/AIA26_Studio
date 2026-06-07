"""
SUGGEST node — generates prioritised fixes from the conflicts found in DETECT.

Suggestion priority comes from the onboarding comfort_weights (weights_override) via
priority_order — no persona category buckets. `persona` is a display label only.
"""

from __future__ import annotations
import json
from nodes._shared.utils import unwrap_mcp_result, persona_display_label


def build_suggest_node(mcp_client):
    def suggest_node(state: dict) -> dict:
        conflicts_json  = state.get("last_conflicts_json", "")
        persona_profile = state.get("persona_profile") or {}
        persona_label   = persona_display_label(persona_profile)
        weights_override = persona_profile.get("comfort_weights")

        if not conflicts_json:
            raise RuntimeError("[suggest] No conflicts available — DETECT must run first.")

        print(f"[suggest] generate_suggestions (persona={persona_label}, custom_weights={bool(weights_override)})")
        args = {"conflicts": conflicts_json, "persona": persona_label}
        if weights_override:
            args["weights_override"] = json.dumps(weights_override)
        raw_output = mcp_client.call_tool("generate_suggestions", args)
        suggestions_json = unwrap_mcp_result(raw_output)
        print(f"[suggest] Suggestions received ({len(suggestions_json)} chars)")

        return {**state, "last_suggestions_json": suggestions_json}

    return suggest_node
