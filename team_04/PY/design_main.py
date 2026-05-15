import argparse

from design_workflow_graph import run_design_workflow
from design_config import load_design_settings
from mcp_client import McpClient


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
    )

    print("\n" + "=" * 60)
    print("DESIGN WORKFLOW RESULT")
    print("=" * 60)
    print(response)
    print("=" * 60)

    mcp_client.close()


if __name__ == "__main__":
    main()
