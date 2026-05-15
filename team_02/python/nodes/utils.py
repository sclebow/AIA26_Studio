"""
nodes/utils.py — Shared helpers used across multiple nodes.

Keep this file small and pure: no LLM calls, no MCP calls, no state mutation.
"""

from __future__ import annotations
import json


def unwrap_mcp_result(tool_output: str) -> str:
    """
    MCP tool responses arrive as: {"result": "<json string>"}

    Unwrap the envelope so downstream nodes receive the actual JSON payload,
    not the outer wrapper. Falls back to the original string if the structure
    is unexpected (already unwrapped, or an error string).

    Example:
        input : '{"result": "{\"comfortScores\": {...}}"}'
        output: '{"comfortScores": {...}}'
    """
    try:
        outer = json.loads(tool_output)
        if isinstance(outer, dict) and "result" in outer:
            inner = outer["result"]
            if isinstance(inner, str):
                # Validate that the inner string is well-formed JSON
                json.loads(inner)
                return inner
    except (json.JSONDecodeError, TypeError):
        pass
    return tool_output
