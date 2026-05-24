"""
nodes/detect.py — DETECT node for the Comfort Copilot state graph.

Pure Python — no LLM. Directly calls the detect_sensorial_conflicts MCP tool.

Always runs after ANALYZE, so last_scores_json is guaranteed to be in state.

Reads from state:
  last_scores_json   (str)  — output of compute_comfort_scores
  persona_detected   (str)  — persona name (e.g. "Elderly 65+")

Writes to state:
  last_conflicts_json  (str)  — unwrapped JSON string from detect_sensorial_conflicts
"""

from __future__ import annotations
from nodes.utils import unwrap_mcp_result


def build_detect_node(mcp_client):
    """Return the detect node function, capturing the MCP client."""

    def detect_node(state: dict) -> dict:
        scores_json = state.get("last_scores_json", "")
        persona     = state.get("persona_detected", "Neutral")

        if not scores_json:
            raise RuntimeError("[detect] No scores found — ANALYZE must run before DETECT.")

        print(f"[detect] Calling detect_sensorial_conflicts (persona={persona})")

        raw_output = mcp_client.call_tool(
            "detect_sensorial_conflicts",
            {
                "scores_json": scores_json,
                "persona":     persona,
            },
        )

        conflicts_json = unwrap_mcp_result(raw_output)
        print(f"[detect] Conflicts received ({len(conflicts_json)} chars)")

        return {
            **state,
            "last_conflicts_json": conflicts_json,
        }

    return detect_node
