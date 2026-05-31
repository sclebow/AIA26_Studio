from __future__ import annotations
import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from _runtime.config import load_settings
from _runtime.mcp_client import McpClient
from _runtime.llm import create_chat_llm, get_llm_response_format
from _runtime.session import detect_existing_session, create_session


@dataclass
class Context:
    """Everything the agent graph needs to run — passed from main.py into graph.py."""
    llm: Any
    mcp_client: McpClient
    tools: list[dict[str, Any]]
    layout_data: dict[str, Any]
    max_iterations: int
    workspace_path: Path
    output_path: Path
    layout_name: str
    # Path to python/knowledge/ — passed to profile_agent and space_type_agent nodes
    knowledge_dir: Path


def bootstrap() -> Context:
    """Load settings, connect to MCP, discover tools, build LLM, and start session.

    Call this once from main.py and pass the returned Context into run_agent().
    Reads --layout <name> from the command line or LAYOUT_FILE env variable.
    """
    settings = load_settings()

    # Resolve team_03/ root — two levels up from this file
    # (_runtime/bootstrap.py → python/ → team_03/)
    team_dir = Path(__file__).resolve().parents[2]

    # ---------------------------------------------------------------------------
    # Resolve layout name from --layout CLI arg or LAYOUT_FILE env variable.
    # CLI takes priority. Env variable allows VS Code launch configs to set it
    # without typing --layout every run.
    # ---------------------------------------------------------------------------
    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--layout", default=None)
    _known, _ = _parser.parse_known_args()

    if not _known.layout:
        env_layout = os.environ.get("LAYOUT_FILE", "").strip()
        if env_layout:
            _known.layout = env_layout.replace(".json", "")
        else:
            raise ValueError(
                "Missing --layout argument. Provide a layout name, e.g. --layout industrial_005"
            )

    # ---------------------------------------------------------------------------
    # Find the layout JSON anywhere under layout/ subfolders.
    # rglob handles nested folders like layout/industrial_100/industrial_005.json
    # ---------------------------------------------------------------------------
    matches = list((team_dir / "layout").rglob(f"{_known.layout}.json"))
    if not matches:
        raise FileNotFoundError(
            f"Layout '{_known.layout}.json' not found anywhere under layout/"
        )
    resolved_layout = matches[0]
    layout_name = _known.layout

    # ---------------------------------------------------------------------------
    # Define workspace and output paths.
    # workspace/ holds the live session file — overwritten on every update.
    # output/ holds the final approved layouts — timestamped, never overwritten.
    # ---------------------------------------------------------------------------
    workspace_path = team_dir / "workspace"
    output_path = team_dir / "output"

    # ---------------------------------------------------------------------------
    # Session management — check if a previous session exists.
    # If yes: ask the user to resume or start fresh.
    # If no: create a new session by copying the base layout to workspace/.
    # The base layout is NEVER modified — all changes go to session_active.json.
    # ---------------------------------------------------------------------------
    if detect_existing_session(workspace_path):
        print(f"\nExisting session found for a previous run.")
        print("Resume existing session? (y/n): ", end="")
        answer = input().strip().lower()

        if answer == "y":
            # Resume — load the last saved state from the workspace file
            session_file = workspace_path / "session_active.json"
            layout_data = json.loads(session_file.read_text(encoding="utf-8"))
            print(f"Resuming session from: {session_file}")
        else:
            # Fresh start — overwrite workspace with base layout
            layout_data = create_session(resolved_layout, workspace_path)
            print(f"Starting fresh session from: {resolved_layout.name}")
    else:
        # No existing session — create one from the base layout
        layout_data = create_session(resolved_layout, workspace_path)
        print(f"New session started from: {resolved_layout.name}")

    # Connect to the Grasshopper MCP server and discover available tools
    mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    mcp_client.initialize()
    tools = mcp_client.list_tools()
    print(f"Discovered MCP tools: {[t.get('name') for t in tools]}")

    # Build the LLM with a structured-output schema tailored to available tools
    llm = create_chat_llm(
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        timeout_seconds=settings.request_timeout_seconds,
        model_kwargs=get_llm_response_format(tools),
    )

    # knowledge/ is at python/knowledge/ — one level up from _runtime/
    knowledge_dir = Path(__file__).resolve().parents[1] / "knowledge"

    return Context(
        llm=llm,
        mcp_client=mcp_client,
        tools=tools,
        layout_data=layout_data,
        max_iterations=settings.max_iterations,
        workspace_path=workspace_path,
        output_path=output_path,
        layout_name=layout_name,
        knowledge_dir=knowledge_dir,
    )
