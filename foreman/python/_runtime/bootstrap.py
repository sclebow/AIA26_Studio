from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from _runtime.config import load_settings
from _runtime.mcp_client import McpClient
from _runtime.llm import create_chat_llm, get_llm_response_format


@dataclass
class Context:
    """Everything the agent graph needs to run — passed from main.py into graph.py."""
    llm: Any
    mcp_client: McpClient
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

    # # Connect to the Grasshopper MCP server and list available tools
    # mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    # mcp_client.initialize()
    # tools = mcp_client.list_tools()
    # print(f"Discovered MCP tools: {[t.get('name') for t in tools]}")

    # Build the LLM with a structured-output schema tailored to the available tools
    llm = create_chat_llm(
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        timeout_seconds=settings.request_timeout_seconds,
        # model_kwargs=get_llm_response_format(tools),
    )

    team_dir = Path(__file__).resolve().parents[2]
    team_name = team_dir.name
    edited_layout_path = team_dir / f"{team_name}_edited_layout.json"

    return Context(
        llm=llm,
        mcp_client=None,
        tools=[],
        layout_data=layout_data,
        max_iterations=settings.max_iterations,
        edited_layout_path=edited_layout_path,
    )
