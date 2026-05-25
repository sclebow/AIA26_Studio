"""
DETECT node — calls MCP detect_sensorial_conflicts on the scores from ANALYZE.
Pure Python, no LLM. Flags senses below persona threshold. Writes last_conflicts_json.
"""

from __future__ import annotations
from nodes._shared.utils import unwrap_mcp_result


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
