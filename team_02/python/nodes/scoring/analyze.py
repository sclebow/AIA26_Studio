"""
ANALYZE node — computes comfort scores for all 6 senses.

Scoring runs purely on the onboarding comfort_weights (weights_override); there are
no more persona category buckets. `persona` is now only a display label echoed into
the output, so we pass the user's real name/role rather than a hardcoded bucket.
"""

from __future__ import annotations
from nodes._shared.utils import unwrap_mcp_result
from nodes._shared.persona_context import persona_scoring_args, derive_context


def build_analyze_node(mcp_client):
    """Return the analyze node function, capturing the MCP client."""

    def analyze_node(state: dict) -> dict:
        layout_json    = state.get("layout_json_string", "")
        persona_profile = state.get("persona_profile") or {}
        target_room_id = state.get("target_room_id")

        if not layout_json:
            raise RuntimeError("[analyze] No layout loaded — cannot compute comfort scores.")

        room_ids = target_room_id if target_room_id else "all"

        # All persona-derived scoring args (label, weights, personality, household
        # context) come from one place so onboarding facts reach the engine intact.
        args = {"layout_json": layout_json, "room_ids": room_ids,
                **persona_scoring_args(persona_profile)}

        print(f"[analyze] compute_comfort_scores (persona={args['persona']}, room_ids={room_ids}, "
              f"custom_weights={'weights_override' in args}, personality={args['personality']}, "
              f"context={derive_context(persona_profile) or 'none'})")

        raw_output = mcp_client.call_tool("compute_comfort_scores", args)
        scores_json = unwrap_mcp_result(raw_output)
        print(f"[analyze] Scores received ({len(scores_json)} chars)")

        return {
            **state,
            "last_scores_json": scores_json,
            # Re-scoring invalidates everything derived from the OLD scores: the
            # conflicts/suggestions and their specialist write-ups. Clear them all so
            # a later follow-up can't answer from stale data (a conflict question
            # after an edit re-detects on the CURRENT layout instead). _finalize must
            # honour these empties for re-scoring actions (no `or`-fallback resurrect).
            "last_conflicts_json":   "",
            "last_suggestions_json": "",
            "conflict_reasoning":    "",
            "suggestion_critique":   "",
        }

    return analyze_node
