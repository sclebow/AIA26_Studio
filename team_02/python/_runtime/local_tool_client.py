"""
local_tool_client.py — in-process replacement for McpClient.

The comfort tools used to live inside Grasshopper and were reached over an
MCP/HTTP bridge. They are pure Python, so they now run in-process. This client
preserves the exact surface McpClient exposed — initialize(), list_tools(),
call_tool(name, arguments), close() — so the agent nodes that call
`ctx.mcp_client.call_tool(...)` need no changes. Rhino/Grasshopper/Swiftlet are
no longer required to run the app.
"""

from __future__ import annotations
import json
from typing import Any

from comfort import (
    compute_comfort_scores,
    detect_sensorial_conflicts,
    generate_suggestions,
)


# Tool catalogue — mirrors what the GH MCP server used to advertise via
# tools/list, so the LLM tool catalogue and bootstrap's discovery print
# keep working unchanged.
_TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "compute_comfort_scores",
        "description": (
            "Compute 6-sense comfort scores (thermal, visual, acoustic, spatial, "
            "olfactory, tactile) for each room of a layout, weighted by persona."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "layout_json": {"type": "string", "description": "Layout as a JSON string."},
                "persona":     {"type": "string", "description": "Persona label, e.g. 'Elderly 65+'."},
                "room_ids":    {"type": "string", "description": "'all' or comma-separated room ids."},
            },
            "required": ["layout_json"],
        },
    },
    {
        "name": "detect_sensorial_conflicts",
        "description": "Flag senses scoring below the persona threshold, per room.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scores_json": {"type": "string", "description": "Output of compute_comfort_scores."},
                "persona":     {"type": "string", "description": "Persona label."},
            },
            "required": ["scores_json"],
        },
    },
    {
        "name": "generate_suggestions",
        "description": "Produce one prioritised, actionable fix per failing sense per room.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conflicts": {"type": "string", "description": "Output of detect_sensorial_conflicts."},
                "persona":   {"type": "string", "description": "Persona label."},
            },
            "required": ["conflicts"],
        },
    },
]


class LocalToolClient:
    """Drop-in replacement for McpClient that runs the comfort tools locally."""

    # name -> callable. Each callable takes the same argument names the MCP
    # tools took and returns a JSON string.
    _DISPATCH = {
        "compute_comfort_scores": compute_comfort_scores,
        "detect_sensorial_conflicts": detect_sensorial_conflicts,
        "generate_suggestions": generate_suggestions,
    }

    def __init__(self, *args, **kwargs) -> None:
        # Accepts (and ignores) the old endpoint/timeout args so call sites that
        # constructed McpClient(endpoint, timeout) still work if reused.
        pass

    def initialize(self) -> None:
        # No connection to open — kept for interface parity with McpClient.
        return None

    def list_tools(self) -> list[dict[str, Any]]:
        return list(_TOOL_DEFS)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        fn = self._DISPATCH.get(name)
        if fn is None:
            raise RuntimeError(
                "Unknown local tool '{}'. Available: {}".format(
                    name, ", ".join(self._DISPATCH)
                )
            )
        result = fn(**arguments)
        # Comfort functions already return JSON strings; guard just in case.
        return result if isinstance(result, str) else json.dumps(result)

    def close(self) -> None:
        return None
