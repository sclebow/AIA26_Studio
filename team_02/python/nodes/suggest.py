"""
nodes/suggest.py — SUGGEST node for the Comfort Copilot state graph.

Pure Python — no LLM. Directly calls the generate_suggestions MCP tool.

Always runs after DETECT, so last_conflicts_json is guaranteed to be in state.

Reads from state:
  last_conflicts_json  (str)  — output of detect_sensorial_conflicts
  persona_detected     (str)  — persona name (e.g. "Elderly 65+")

Writes to state:
  last_suggestions_json  (str)  — unwrapped JSON string from generate_suggestions
"""

from __future__ import annotations
from nodes.utils import unwrap_mcp_result


def build_suggest_node(mcp_client):
    """Return the suggest node function, capturing the MCP client."""

    def suggest_node(state: dict) -> dict:
        conflicts_json = state.get("last_conflicts_json", "")
        persona        = state.get("persona_detected", "Neutral")

        if not conflicts_json:
            raise RuntimeError("[suggest] No conflicts found — DETECT must run before SUGGEST.")

        print(f"[suggest] Calling generate_suggestions (persona={persona})")

        raw_output = mcp_client.call_tool(
            "generate_suggestions",
            {
                "conflicts": conflicts_json,
                "persona":   persona,
            },
        )

        suggestions_json = unwrap_mcp_result(raw_output)
        print(f"[suggest] Suggestions received ({len(suggestions_json)} chars)")

        return {
            **state,
            "last_suggestions_json": suggestions_json,
        }

    return suggest_node
