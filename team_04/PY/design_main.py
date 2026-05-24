import argparse
import json
from pathlib import Path

from design_workflow_graph import run_design_workflow
from design_config import load_design_settings
from mcp_client import McpClient
import plan_agent as pa
from plan_agent import (
    format_plan_agent_response,
    generate_plan_agent_payload,
    should_request_clarification,
)
from tool_node import create_chat_llm


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Site design optimization workflow using LangGraph + MCP"
    )
    parser.add_argument("prompt", help="User prompt for the design task")
    parser.add_argument(
        "--feedback",
        help="Optional feedback to refine the design",
        default="",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_design_settings()

    layout_schema_path = Path(__file__).with_name("layout_schema.json")
    try:
        layout_schema = json.loads(layout_schema_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        layout_schema = {}

    print("=" * 60)
    print("SITE DESIGN OPTIMIZATION WORKFLOW")
    print("=" * 60)
    print(f"Provider: {settings.llm_provider}")
    print(f"Model: {settings.llm_model}")
    print(f"Base URL: {settings.base_url}")
    print(f"DEBUG_GRAPH: {settings.debug_graph}")
    print(f"MCP Config Path: {settings.mcp_config_path}")
    print(f"MCP Server Key: {settings.mcp_server_key}")
    print(f"MCP Endpoint: {settings.mcp_endpoint}")
    print(f"Max Iterations: {settings.max_iterations}")
    print(f"Max Design Iterations: {settings.max_design_iterations}")
    print("=" * 60)

    # Initialize MCP client
    mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    mcp_client.initialize()
    tools = mcp_client.list_tools()
    print(f"\nDiscovered {len(tools)} MCP tools")
    for tool in tools:
        print(f"  - {tool.get('name', 'unknown')}")
    print()

    # Plan Agent: prepare the strategy before the existing workflow starts
    # Use a shorter timeout for the planning LLM call so the script fails fast
    planning_timeout = min(settings.request_timeout_seconds, 15.0)
    planning_llm = create_chat_llm(
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        timeout_seconds=planning_timeout,
    )

    try:
        planning_context = generate_plan_agent_payload(
            llm=planning_llm,
            user_prompt=args.prompt,
            tools=tools,
            layout_schema=layout_schema,
            dbg=lambda message: print(message) if settings.debug_graph else None,
        )
    except Exception as e:
        print(f"[warning] Plan agent LLM failed or timed out: {e}")
        print("Falling back to deterministic planning logic.")
        planning_context = pa._fallback_plan(args.prompt, pa.build_shape_generation_state(args.prompt))

    print("\n" + "=" * 60)
    print("PLAN AGENT")
    print("=" * 60)
    print(format_plan_agent_response(planning_context))
    print("=" * 60)

    if should_request_clarification(planning_context):
        clarification = str(planning_context.get("clarification_question", "")).strip()
        if clarification:
            print(f"\nClarification needed: {clarification}")
        mcp_client.close()
        return

    # Run the workflow
    response = run_design_workflow(
        user_prompt=args.prompt,
        tools=tools,
        mcp_client=mcp_client,
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        debug_graph=settings.debug_graph,
        timeout_seconds=settings.request_timeout_seconds,
        max_iterations=settings.max_iterations,
        planning_context=planning_context,
    )

    print("\n" + "=" * 60)
    print("DESIGN WORKFLOW RESULT")
    print("=" * 60)
    print(response)
    print("=" * 60)

    mcp_client.close()


if __name__ == "__main__":
    main()
