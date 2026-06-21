"""
CLI entry point for the Industrial Spatial Flow agent.

Two ways to run:

  1. Interactive / local (loads a layout file from team_03/layout/):
       python main.py --layout industrial_005 --prompt "place a cnc in the workshop"
       python main.py --layout industrial_005 "place a cnc in the workshop"   # positional prompt

  2. Orchestrator subprocess (layout supplied as a JSON string, no file needed):
       python main.py --prompt "add a window to the south wall" --layout_json '{ ...layout... }'

When --layout_json is provided the orchestrator-supplied layout is used directly
(it is written to the workspace session, so the base files are untouched). The
agent's checkpoints still read from the console, so an orchestrator can hold a
back-and-forth conversation over stdin/stdout while the run is in progress.

Output is printed in a stable, machine-readable structure for orchestrators:

    Final Response:
    <agent response>

    Edited Layout JSON:
    <edited layout JSON or "No layout changes">
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

from _runtime.bootstrap import bootstrap, Context
from _runtime.config import load_settings
from _runtime.mcp_client import McpClient
from _runtime.llm import create_chat_llm, get_llm_response_format
from _runtime.session import save_session
from graph import run_agent


def _build_context_from_layout(layout_data: dict) -> Context:
    """Build a Context from an orchestrator-provided layout, bypassing the base
    file lookup and the "resume session?" prompt that bootstrap() does. The layout
    is written to the workspace session so all mutations stay isolated there."""
    settings = load_settings()
    python_dir = Path(__file__).resolve().parent          # team_03/python
    team_dir = python_dir.parent                           # team_03
    workspace_path = team_dir / "workspace"
    output_path = team_dir / "output"
    workspace_path.mkdir(parents=True, exist_ok=True)

    # Persist the orchestrator layout as the live session (base files untouched).
    save_session(layout_data, workspace_path)
    layout_name = str(layout_data.get("layoutId") or "cli_layout")

    mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    mcp_client.initialize()
    tools = mcp_client.list_tools()
    print(f"Discovered MCP tools: {[t.get('name') for t in tools]}")

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
        workspace_path=workspace_path,
        output_path=output_path,
        layout_name=layout_name,
        knowledge_dir=python_dir / "knowledge",
    )


def _read_edited_layout(ctx: Context, start_time: float) -> "dict | None":
    """Best-effort read of the layout after the run. Prefer the live workspace
    session; if it was closed (the user approved → moved to output/ and deleted
    the workspace file), fall back to the newest output file from this run."""
    active = Path(ctx.workspace_path) / "session_active.json"
    if active.exists():
        try:
            return json.loads(active.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        out_dir = Path(ctx.output_path)
        candidates = sorted(
            (p for p in out_dir.glob(f"{ctx.layout_name}_*.json")
             if p.stat().st_mtime >= start_time - 1),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return json.loads(candidates[0].read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _print_result(response: str, edited_layout: "dict | None") -> None:
    """Print the stable, machine-readable output block for orchestrators."""
    safe = (response or "").encode("ascii", errors="replace").decode("ascii")
    print("\nFinal Response: ")
    print(safe)
    print("\nEdited Layout JSON:")
    if edited_layout is not None:
        print(json.dumps(edited_layout, indent=2, ensure_ascii=False))
    else:
        print("No layout changes")


def main():
    parser = argparse.ArgumentParser(description="Run the Industrial Spatial Flow agent.")
    parser.add_argument("--prompt", default=None,
                        help="Instruction for the agent (required).")
    parser.add_argument("--layout_json", default=None,
                        help="Optional layout as a JSON string (orchestrator-provided). "
                             "When set, it overrides the on-disk layout.")
    parser.add_argument("--layout", default=None,
                        help="Layout name to load from team_03/layout/ when --layout_json "
                             "is not given, e.g. industrial_005.")
    # Backward-compatible positional prompt (older usage passed the prompt directly).
    parser.add_argument("prompt_positional", nargs="?", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    prompt_text = args.prompt if args.prompt is not None else args.prompt_positional
    if not prompt_text:
        print("Error: a prompt is required. Use --prompt \"<instruction>\".", file=sys.stderr)
        sys.exit(2)

    # Parse --layout_json up front so a malformed string fails clearly (non-zero exit)
    # before any agent work begins.
    layout_override = None
    if args.layout_json:
        try:
            layout_override = json.loads(args.layout_json)
        except (json.JSONDecodeError, TypeError) as exc:
            print(f"Error: --layout_json is not valid JSON: {exc}", file=sys.stderr)
            sys.exit(2)
        if not isinstance(layout_override, dict):
            print("Error: --layout_json must be a JSON object (the layout).", file=sys.stderr)
            sys.exit(2)

    def _close(ctx: "Context | None") -> None:
        if ctx is not None:
            try:
                ctx.mcp_client.close()
            except Exception:
                pass

    ctx = None
    input_layout = None
    start_time = time.time()
    try:
        # Initialize context. With --layout_json, use the orchestrator layout
        # directly; otherwise bootstrap() resolves --layout / LAYOUT_FILE as before.
        if layout_override is not None:
            ctx = _build_context_from_layout(layout_override)
        else:
            ctx = bootstrap()

        # Easter egg: only in interactive (non-orchestrator) mode so machine output stays clean.
        if layout_override is None and random.random() < 0.12:
            print("\nHope you're not Ramy... what can I do for you?")

        # Snapshot the input layout so we can tell whether the run changed anything.
        input_layout = json.loads(json.dumps(ctx.layout_data))
        start_time = time.time()

        response = run_agent(prompt_text, ctx)
    except Exception as exc:
        # Always emit a parseable block, even on failure, so the orchestrator
        # never gets a bare crash.
        _close(ctx)
        _print_result(f"Agent error: {exc}", None)
        sys.exit(1)

    _close(ctx)
    edited = _read_edited_layout(ctx, start_time)
    changed = edited is not None and edited != input_layout
    _print_result(response, edited if changed else None)


if __name__ == "__main__":
    main()
