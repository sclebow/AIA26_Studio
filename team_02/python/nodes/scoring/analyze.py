"""
ANALYZE node — computes comfort scores for all 6 senses.

Scoring runs purely on the onboarding comfort_weights (weights_override); there are
no more persona category buckets. `persona` is now only a display label echoed into
the output, so we pass the user's real name/role rather than a hardcoded bucket.
"""

from __future__ import annotations
import json
from nodes._shared.utils import unwrap_mcp_result, persona_display_label


def build_analyze_node(mcp_client):
    """Return the analyze node function, capturing the MCP client."""

    def analyze_node(state: dict) -> dict:
        layout_json    = state.get("layout_json_string", "")
        persona_profile = state.get("persona_profile") or {}
        target_room_id = state.get("target_room_id")

        if not layout_json:
            raise RuntimeError("[analyze] No layout loaded — cannot compute comfort scores.")

        room_ids = target_room_id if target_room_id else "all"
        persona_label = persona_display_label(persona_profile)

        # Pass custom comfort weights from onboarding if available
        weights_override = persona_profile.get("comfort_weights")

        # Personality / arousal axis (introvert −1 … extrovert +1); neutral until onboarding captures it.
        pers = persona_profile.get("personality", 0)
        if isinstance(pers, str):
            pers = {"introvert": -1.0, "extrovert": 1.0}.get(pers.strip().lower(), 0.0)
        try:
            personality = float(pers or 0)
        except (TypeError, ValueError):
            personality = 0.0

        print(f"[analyze] compute_comfort_scores (persona={persona_label}, room_ids={room_ids}, custom_weights={bool(weights_override)}, personality={personality})")

        args = {
            "layout_json": layout_json,
            "persona":     persona_label,
            "room_ids":    room_ids,
            "personality": personality,
        }
        if weights_override:
            args["weights_override"] = json.dumps(weights_override)

        raw_output = mcp_client.call_tool("compute_comfort_scores", args)
        scores_json = unwrap_mcp_result(raw_output)
        print(f"[analyze] Scores received ({len(scores_json)} chars)")

        return {
            **state,
            "last_scores_json": scores_json,
            # Clear stale conflict/suggestion data when re-scoring
            "last_conflicts_json":   "",
            "last_suggestions_json": "",
        }

    return analyze_node
