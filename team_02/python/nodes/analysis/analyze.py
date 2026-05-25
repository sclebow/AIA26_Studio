"""
ANALYZE node — calls MCP compute_comfort_scores for all 6 senses across all rooms.
Pure Python, no LLM. Writes last_scores_json to state.
"""

from __future__ import annotations
from nodes._shared.utils import unwrap_mcp_result


def build_analyze_node(mcp_client):
    """Return the analyze node function, capturing the MCP client."""

    def analyze_node(state: dict) -> dict:
        layout_json    = state.get("layout_json_string", "")
        persona        = state.get("persona_detected", "Neutral")
        target_room_id = state.get("target_room_id")  # None means all rooms

        if not layout_json:
            raise RuntimeError("[analyze] No layout loaded -- cannot compute comfort scores.")

        room_ids = target_room_id if target_room_id else "all"
        print("[analyze] Calling compute_comfort_scores (persona={}, room_ids={})".format(persona, room_ids))

        raw_output = mcp_client.call_tool(
            "compute_comfort_scores",
            {
                "layout_json": layout_json,
                "persona":     persona,
                "room_ids":    room_ids,
            },
        )

        scores_json = unwrap_mcp_result(raw_output)
        print("[analyze] Scores received ({} chars)".format(len(scores_json)))

        return {
            **state,
            "last_scores_json": scores_json,
        }

    return analyze_node
