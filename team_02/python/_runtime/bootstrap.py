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
    """Everything the agent graph needs to run -- passed from main.py into graph.py."""
    llm: Any          # Structured-output LLM (JSON schema enforced) -- reserved for future tool-calling
    llm_simple: Any   # Plain LLM (no response_format) -- used by chitchat, respond, route_intent
    mcp_client: McpClient
    tools: list[dict[str, Any]]
    layout_data: dict[str, Any]
    max_iterations: int
    edited_layout_path: Path
    layout_input_dir: Path   # Source layouts -- read-only input  (randomized_layouts/)
    layout_output_dir: Path  # Analysis results -- write destination (resulting_layout/)


# Python-side pseudo-tool. Not an MCP tool -- it's intercepted in nodes/tools.py
# and runs locally (terminal prompt -> file read -> state update). Listed in the
# tool catalog so the LLM knows it exists and can choose to call it.
SELECT_LAYOUT_TOOL: dict[str, Any] = {
    "name": "select_layout",
    "description": (
        "Prompt the user (in the terminal) to pick a layout JSON file from the "
        "layout_input/ directory and load it into the agent's context. Takes no "
        "arguments. Call this once, before any other tool, when (and only when) "
        "the user's request requires a layout. After this returns successfully, "
        "subsequent layout-dependent tool calls will operate on the chosen layout."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
}


def select_layout(repo_root: Path) -> Path:
    """Discover available layout files and prompt the user to select one.

    Searches for JSON files in layout_input/ directory.
    Returns the Path to the selected layout file.
    """
    layout_dir = repo_root / "layout_input"

    layout_files = sorted(layout_dir.glob("*.json"))

    if not layout_files:
        raise FileNotFoundError("No JSON files found in {}".format(layout_dir))

    if len(layout_files) == 1:
        print("Using layout: {}".format(layout_files[0].name))
        return layout_files[0]

    print("\nAvailable layouts:")
    for i, file in enumerate(layout_files, 1):
        print("  {}. {}".format(i, file.name))

    while True:
        try:
            choice = input("\nSelect a layout (enter number): ").strip()
            index = int(choice) - 1
            if 0 <= index < len(layout_files):
                selected = layout_files[index]
                print("Selected: {}\n".format(selected.name))
                return selected
            else:
                print("Please enter a number between 1 and {}".format(len(layout_files)))
        except ValueError:
            print("Invalid input. Please enter a number.")


def bootstrap(layout_path: Path | None = None) -> Context:
    """Load settings, connect to the MCP server, discover tools, and build the LLM.

    Call this once from main.py and pass the returned Context into run_agent().

    Args:
        layout_path: Optional Path to a specific layout file to pre-load. If
                    omitted (the normal case), no layout is loaded at startup --
                    the agent will call the select_layout pseudo-tool, which
                    prompts the user in the terminal, when (and only when) the
                    request actually needs a layout.
    """
    settings = load_settings()

    # Source layouts -- read-only. Resolves to <team_02>/randomized_layouts/
    # These files are never overwritten by the agent.
    team_dir = Path(__file__).resolve().parents[2]
    layout_input_dir  = team_dir / "randomized_layouts"  # source -- never overwritten
    layout_output_dir = team_dir / "resulting_layout"    # analysis results written here

    # Optionally pre-load a specific file (kept for tests / scripted use).
    if layout_path is not None:
        layout_data: dict[str, Any] = json.loads(layout_path.read_text(encoding="utf-8"))
    else:
        layout_data = {}

    # Connect to the Grasshopper MCP server and list available tools
    mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    mcp_client.initialize()
    mcp_tools = mcp_client.list_tools()
    print("Discovered MCP tools: {}".format([t.get("name") for t in mcp_tools]))

    # Combine MCP tools with our Python-side pseudo-tool. From the LLM's
    # perspective they are all just tools it can choose to call; the tool node
    # routes select_layout locally instead of forwarding it to the MCP server.
    tools = mcp_tools + [SELECT_LAYOUT_TOOL]
    print("Plus Python-side pseudo-tool: {}".format(SELECT_LAYOUT_TOOL["name"]))

    # Structured LLM -- JSON schema enforced (reserved for future tool-calling nodes)
    llm = create_chat_llm(
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        timeout_seconds=settings.request_timeout_seconds,
        model_kwargs=get_llm_response_format(tools),
    )

    # Plain LLM -- no response_format, free-form text output.
    # Used by chitchat, respond, and route_intent nodes via call_llm_simple().
    llm_simple = create_chat_llm(
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        timeout_seconds=settings.request_timeout_seconds,
        model_kwargs=None,
    )

    team_name = team_dir.name
    edited_layout_path = team_dir / "{}_edited_layout.json".format(team_name)

    return Context(
        llm=llm,
        llm_simple=llm_simple,
        mcp_client=mcp_client,
        tools=tools,
        layout_data=layout_data,
        max_iterations=settings.max_iterations,
        edited_layout_path=edited_layout_path,
        layout_input_dir=layout_input_dir,
        layout_output_dir=layout_output_dir,
    )
