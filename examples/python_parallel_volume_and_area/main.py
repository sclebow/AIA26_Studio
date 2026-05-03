import argparse

from agent_graph import run_agent
from config import load_settings
from mcp_client import McpClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a simple LangGraph + MCP agent.")
    parser.add_argument("prompt", help="User prompt for the agent")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()

    print(f"Provider: {settings.llm_provider}")
    print(f"Model: {settings.llm_model}")
    print(f"Base URL: {settings.base_url}")
    print(f"DEBUG_GRAPH: {settings.debug_graph}")
    print(f"MCP Config Path: {settings.mcp_config_path}")
    print(f"MCP Server Key: {settings.mcp_server_key}")
    print(f"MCP Endpoint: {settings.mcp_endpoint}")

    mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    mcp_client.initialize()
    tools = mcp_client.list_tools()
    print(f"Discovered tools: {len(tools)}")

    response = run_agent(
        user_prompt=args.prompt,
        tools=tools,
        mcp_client=mcp_client,
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        debug_graph=settings.debug_graph,
        timeout_seconds=settings.request_timeout_seconds,
        max_iterations=settings.max_iterations,
        llm_provider=settings.llm_provider,
    )
    print("\nAgent response:\n")
    # Replace problematic Unicode characters for Windows terminal compatibility
    safe_response = response.encode('ascii', errors='replace').decode('ascii')
    print(safe_response)

    mcp_client.close()


if __name__ == "__main__":
    main()