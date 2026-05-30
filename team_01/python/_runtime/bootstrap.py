from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from _runtime.config import load_settings
# from _runtime.mcp_client import McpClient  # not needed without MCP
from _runtime.llm import create_chat_llm, get_llm_response_format


# ── No-MCP stub — stands in for McpClient when Grasshopper is not running ────
class _NoMcpClient:
    def initialize(self): pass
    def close(self): pass
    def call_tool(self, name, arguments): raise RuntimeError(f"MCP not connected — cannot call {name!r}")
# ─────────────────────────────────────────────────────────────────────────────

# Hardcoded tool definition for tag_and_audit (normally discovered via MCP)
_TAG_AND_AUDIT_TOOL = {
    "name": "tag_and_audit",
    "description": "Generate structural column/beam layout options derived from the floor plan walls.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "layout_json":  {"type": "string",  "description": "The floor plan JSON string."},
            "typology":     {"type": "string",  "description": "column_grid | perimeter_load_bearing | shear_wall"},
            "grid_spacing": {"type": "number",  "description": "Grid spacing in metres (default 4.0)"},
        },
        "required": ["layout_json"],
    },
}


@dataclass
class Context:
    """Everything the agent graph needs to run — passed from main.py into graph.py."""
    llm: Any
    mcp_client: Any
    tools: list[dict[str, Any]]
    layout_data: dict[str, Any]
    max_iterations: int
    edited_layout_path: Path


def bootstrap() -> Context:
    """Load settings, connect to the MCP server, discover tools, and build the LLM.

    Call this once from main.py and pass the returned Context into run_agent().
    """
    settings = load_settings()

    # Read the layout schema that will be given to the agent as context (shared at repo root)
    repo_root = Path(__file__).resolve().parents[3]
    layout_path = repo_root / "layout_input" / "layout_schema.json"
    layout_data: dict[str, Any] = json.loads(layout_path.read_text(encoding="utf-8"))

    # ── MCP connection — commented out; not needed when running without Grasshopper ──
    # mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    # mcp_client.initialize()
    # tools = mcp_client.list_tools()
    # print(f"Discovered MCP tools: {[t.get('name') for t in tools]}")
    mcp_client = _NoMcpClient()
    tools = [_TAG_AND_AUDIT_TOOL]
    print(f"[no-MCP] Available tools: {[t['name'] for t in tools]}")
    # ─────────────────────────────────────────────────────────────────────────────

    # Build the LLM with a structured-output schema tailored to the available tools
    llm = create_chat_llm(
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        timeout_seconds=settings.request_timeout_seconds,
        model_kwargs=get_llm_response_format(tools),
    )

    team_dir = Path(__file__).resolve().parents[2]
    team_name = team_dir.name
    edited_layout_path = team_dir / f"{team_name}_edited_layout.json"

    return Context(
        llm=llm,
        mcp_client=mcp_client,
        tools=tools,
        layout_data=layout_data,
        max_iterations=settings.max_iterations,
        edited_layout_path=edited_layout_path,
    )
