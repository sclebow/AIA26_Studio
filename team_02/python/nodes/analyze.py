"""
nodes/analyze.py -- ANALYZE node for the Comfort Copilot state graph.

Pure Python -- no LLM. Directly calls the compute_comfort_scores MCP tool.

Reads from state:
  layout_json_string  (str)       -- full layout JSON
  persona_detected    (str)       -- persona name (e.g. "Elderly 65+")
  target_room_id      (str|None)  -- specific room ID, or None for all rooms

Writes to state:
  last_scores_json    (str)  -- unwrapped JSON string from compute_comfort_scores
"""

from __future__ import annotations
from nodes.utils import unwrap_mcp_result


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
