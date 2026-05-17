from __future__ import annotations

import argparse

from langchain_openai import ChatOpenAI

from .config import load_initial_layout, load_settings
from .decision_engine import OpenAIDecisionEngine, RuleBasedPlanner
from .graph import run_agent
from .mcp_client import CompositeToolClient, HttpMcpClient, build_default_local_tool_client
from .tool_catalog import ToolCatalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Team 04 TerraPilot agent.")
    parser.add_argument("prompt", help="User prompt for the site-design workflow")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    initial_layout = load_initial_layout(settings.initial_layout_path)

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
        final_state = run_agent(
            user_prompt=args.prompt,
            decision_engine=engine,
            tool_client=client,
            catalog=catalog,
            initial_layout=initial_layout,
            max_optimization_cycles=settings.max_optimization_cycles,
            planner=planner,
        )
        final_layout = final_state.get("layout_json")
        if isinstance(final_layout, str) and final_layout.strip():
            settings.output_layout_path.write_text(final_layout, encoding="utf-8")
        final_response = final_state.get("final_response") or "Workflow completed without a final response."
        print(final_response)
    finally:
        client.close()


if __name__ == "__main__":
    main()