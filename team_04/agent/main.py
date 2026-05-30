from __future__ import annotations

import argparse
import json
import sys

from langchain_openai import ChatOpenAI

from .config import load_initial_layout, load_settings
from .decision_engine import OpenAIDecisionEngine, RuleBasedPlanner
from .graph import run_agent
from .mcp_client import CompositeToolClient, HttpMcpClient, build_default_local_tool_client
from .tool_catalog import ToolCatalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Team 04 TerraPilot agent.")
    parser.add_argument("--prompt", required=True, help="User prompt for the site-design workflow")
    parser.add_argument(
        "--layout_json",
        default=None,
        help="Optional JSON string representing the current layout (overrides the default layout file)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Parse --layout_json when provided
    override_layout: dict | None = None
    if args.layout_json is not None:
        try:
            override_layout = json.loads(args.layout_json)
        except json.JSONDecodeError as exc:
            print(f"Error: --layout_json is not valid JSON: {exc}", file=sys.stderr)
            sys.exit(1)

    settings = load_settings()
    # Use orchestrator-provided layout if given; otherwise fall back to the default file
    initial_layout = override_layout if override_layout is not None else load_initial_layout(settings.initial_layout_path)

    local_client = build_default_local_tool_client()
    mcp_client = HttpMcpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    mcp_client.initialize()
    client = CompositeToolClient([local_client, mcp_client])
    try:
        discovered_tools = client.list_tools()
        catalog = ToolCatalog.from_discovered_tools(discovered_tools)
        llm = ChatOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            model=settings.llm_model,
            timeout=settings.request_timeout_seconds,
            temperature=0,
        )
        engine = OpenAIDecisionEngine(llm=llm)
        planner = RuleBasedPlanner()

        prompt_text = args.prompt
        current_layout = initial_layout
        final_layout_str: str | None = None

        # Main loop — re-runs the agent when it asks for clarification
        while True:
            final_state = run_agent(
                user_prompt=prompt_text,
                decision_engine=engine,
                tool_client=client,
                catalog=catalog,
                initial_layout=current_layout,
                max_optimization_cycles=settings.max_optimization_cycles,
                planner=planner,
            )

            final_layout_str = final_state.get("layout_json")
            if isinstance(final_layout_str, str) and final_layout_str.strip():
                settings.output_layout_path.write_text(final_layout_str, encoding="utf-8")

            final_response = (
                final_state.get("final_response") or "Workflow completed without a final response."
            )

            # If the agent is waiting for human clarification, ask via stdin and loop back
            human_request = final_state.get("human_request")
            if human_request:
                print(human_request, flush=True)
                try:
                    user_clarification = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                prompt_text = f"{prompt_text}\nUser clarification: {user_clarification}"
                # Carry forward any partial layout produced so far
                if isinstance(final_layout_str, str) and final_layout_str.strip():
                    try:
                        current_layout = json.loads(final_layout_str)
                    except json.JSONDecodeError:
                        pass
                continue

            # No further clarification needed — exit loop
            break

        # ── Stable machine-readable output for orchestrators ──────────────────
        print("Final Response:")
        print(final_response)
        print()
        print("Edited Layout JSON:")
        if isinstance(final_layout_str, str) and final_layout_str.strip():
            try:
                print(json.dumps(json.loads(final_layout_str), indent=2))
            except json.JSONDecodeError:
                print(final_layout_str)
        else:
            print("No layout changes")

    finally:
        client.close()


if __name__ == "__main__":
    main()