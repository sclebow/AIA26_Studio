import argparse
import sys
from unittest.mock import Mock, patch

from design_workflow_graph import run_design_workflow
from design_config import load_design_settings
from mcp_client import McpClient


class DummyLLM:
    """Dummy LLM that returns pre-defined JSON responses for testing"""
    
    def __init__(self):
        self.call_count = 0
        self.responses = [
            # First sequence: suggestion
            '{"action": "suggest", "reasoning": "Initial analysis phase"}',
            '{"suggestions": ["rectangular layout", "solar orientation optimization"], "confidence": 0.85}',
            # Evaluation
            '{"action": "evaluate", "reasoning": "Evaluate current design"}',
            '{"score": 0.78, "metrics": {"efficiency": 0.8, "compliance": 0.75}, "issues": ["setback too small"]}',
            # Optimization
            '{"action": "optimize", "reasoning": "Improve design parameters"}',
            '{"adjustments": {"rotation": 45, "setback": 5.5, "coverage": 0.35}, "new_score": 0.82}',
            # Explanation
            '{"action": "explain", "reasoning": "Explain the design"}',
            '{"explanation": "The optimized layout maximizes solar gain while maintaining setback compliance"}',
            # Finish
            '{"action": "final", "reasoning": "Design optimization complete"}',
        ]
    
    def invoke(self, messages):
        """Return dummy responses in sequence"""
        response = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        print(f"[DUMMY LLM] Call #{self.call_count}: {response[:80]}")
        
        # Return a mock message object
        mock_message = Mock()
        mock_message.content = response
        return mock_message


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Site design optimization workflow using LangGraph + MCP (TEST MODE)"
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
    print("SITE DESIGN OPTIMIZATION WORKFLOW (TEST MODE - DUMMY LLM)")
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
    tools = []
    try:
        mcp_client.initialize()
        tools = mcp_client.list_tools()
        print(f"\nDiscovered {len(tools)} MCP tools")
        for tool in tools:
            print(f"  - {tool.get('name', 'unknown')}")
        print()
    except Exception as exc:
        print(
            "\n[WARN] MCP server not reachable. Continuing with empty tools list."
        )
        print(f"[WARN] MCP error: {type(exc).__name__}: {exc}\n")

    # Run the workflow with dummy LLM
    print("[TEST] Starting workflow with dummy LLM responses...\n")
    
    try:
        # Patch the LLM creation to use dummy LLM
        # Also patch input() to provide empty feedback to avoid blocking
        with patch('design_workflow_graph.create_chat_llm', return_value=DummyLLM()):
            with patch('builtins.input', return_value='no'):  # Auto-respond "no" to feedback prompts
                response = run_design_workflow(
                    user_prompt=args.prompt,
                    tools=tools,
                    mcp_client=mcp_client,
                    api_key=settings.api_key,
                    base_url=settings.base_url,
                    llm_model=settings.llm_model,
                    debug_graph=True,  # Enable debug for testing
                    timeout_seconds=settings.request_timeout_seconds,
                    max_iterations=min(settings.max_iterations, 2),  # Limit to 2 iterations for testing
                )
        
        print("\n" + "=" * 60)
        print("WORKFLOW COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"\nFinal Response:\n{response}\n")
        
    except Exception as e:
        print(f"\n[ERROR] Workflow failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
