from __future__ import annotations
import json
from typing import Any


def _slim_layout(layout_data: dict) -> dict:
    # Send only what the LLM needs for spatial reasoning.
    # Windows, MEP, and structure are stripped to reduce tokens — they matter
    # for visualization and engineering but not for object placement decisions.
    return {
        "layoutId": layout_data.get("layoutId"),
        "rooms": [
            {
                "id":       r.get("id"),
                "name":     r.get("name"),
                "geometry": r.get("geometry"),
            }
            for r in layout_data.get("rooms", [])
        ],
        "doors": [
            {
                "id":       d.get("id"),
                "name":     d.get("name"),
                "geometry": d.get("geometry"),
                "connects": d.get("attributes", {}).get("connectsRooms", []),
            }
            for d in layout_data.get("doors", [])
        ],
        "furniture": layout_data.get("furniture", []),
    }


def _format_tool_catalog(tools: list[dict[str, Any]]) -> str:
    lines = []
    for tool in tools:
        name = tool.get("name", "<unknown>")
        description = tool.get("description", "")
        schema = json.dumps(tool.get("inputSchema", {}))
        lines.append(f"- {name}: {description} | inputSchema={schema}")
    return "\n".join(lines)
