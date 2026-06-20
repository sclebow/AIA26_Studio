"""
local_tool_client.py — in-process replacement for McpClient.
Updated: compute_comfort_scores now accepts weights_override for custom persona weights.
"""

from __future__ import annotations
import json
from typing import Any

from comfort import (
    compute_comfort_scores,
    detect_sensorial_conflicts,
    generate_suggestions,
)

_TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "compute_comfort_scores",
        "description": "Compute 6-sense comfort scores per room, persona-weighted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layout_json":      {"type": "string"},
                "persona":          {"type": "string"},
                "room_ids":         {"type": "string"},
                "weights_override": {"type": "string", "description": "JSON dict of {sense: multiplier} from onboarding."},
                "personality":      {"type": "number", "description": "Arousal axis -1 (introvert) .. +1 (extrovert)."},
                "context":          {"type": "string", "description": "JSON dict of household-context flags, e.g. {\"elderly\": true, \"pets\": true}."},
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
                "scores_json": {"type": "string"},
                "persona":     {"type": "string"},
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
                "conflicts": {"type": "string"},
                "persona":   {"type": "string"},
            },
            "required": ["conflicts"],
        },
    },
]


class LocalToolClient:
    _DISPATCH = {
        "compute_comfort_scores":    compute_comfort_scores,
        "detect_sensorial_conflicts": detect_sensorial_conflicts,
        "generate_suggestions":      generate_suggestions,
    }

    def __init__(self, *args, **kwargs) -> None:
        pass

    def initialize(self) -> None:
        return None

    def list_tools(self) -> list[dict[str, Any]]:
        return list(_TOOL_DEFS)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        fn = self._DISPATCH.get(name)
        if fn is None:
            raise RuntimeError(f"Unknown local tool '{name}'. Available: {', '.join(self._DISPATCH)}")
        result = fn(**arguments)
        return result if isinstance(result, str) else json.dumps(result)

    def close(self) -> None:
        return None
