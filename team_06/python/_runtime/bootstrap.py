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
    reference_layout_path: Path
    input_layout_path: Path

def bootstrap() -> Context:
    """Load settings, connect to the MCP server, discover tools, and build the LLM.

    Call this once from main.py and pass the returned Context into run_agent().
    """
    settings = load_settings()

    # Get paths
    repo_root = Path(__file__).resolve().parents[3]
    team_dir = Path(__file__).resolve().parents[2]
    team_name = team_dir.name
    
    edited_layout_path = team_dir / f"{team_name}_edited_layout.json"
    reference_layout_path = team_dir / f"{team_name}_reference_layout.json"
    input_layout_path = team_dir / f"{team_name}_input_layout.json"
    
    # Load layout with priority: edited → reference → input
    if edited_layout_path.exists():
        layout_data = json.loads(edited_layout_path.read_text(encoding="utf-8"))
        print(f"[bootstrap] Loaded layout: edited_layout ({team_name}_edited_layout.json)")
    elif reference_layout_path.exists():
        layout_data = json.loads(reference_layout_path.read_text(encoding="utf-8"))
        print(f"[bootstrap] Loaded layout: reference_layout ({team_name}_reference_layout.json)")
    else:
        layout_data = json.loads(input_layout_path.read_text(encoding="utf-8"))
        print(f"[bootstrap] Loaded layout: input_layout ({team_name}_input_layout.json)")

    # Connect to the Grasshopper MCP server and list available tools
    # Make this optional - if MCP server is not available, only local tools will work
    mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    tools = []
    mcp_tool_names = []
    
    try:
        mcp_client.initialize()
        tools = mcp_client.list_tools()
        mcp_tool_names = [t.get('name') for t in tools]
        print(f"[bootstrap] Discovered MCP tools: {mcp_tool_names}")
    except Exception as e:
        print(f"[bootstrap] Warning: Could not connect to MCP server: {type(e).__name__}")
        print(f"[bootstrap] Continuing with local tools only...")

    # Build the LLM with a structured-output schema tailored to the available tools
    llm = create_chat_llm(
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        timeout_seconds=settings.request_timeout_seconds,
        model_kwargs=get_llm_response_format(tools),
    )

    return Context(
        llm=llm,
        mcp_client=mcp_client,
        tools=tools,
        layout_data=layout_data,
        max_iterations=settings.max_iterations,
        edited_layout_path=edited_layout_path,
        reference_layout_path=reference_layout_path,
        input_layout_path=input_layout_path,
    )
