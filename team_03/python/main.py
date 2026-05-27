import argparse
from _runtime.bootstrap import bootstrap
from graph import run_agent


def main():

    # Process the command line arguments (the user instruction)
    parser = argparse.ArgumentParser(description="Run the Grasshopper MCP agent.")
    parser.add_argument("prompt", help="Your instruction for the agent (e.g. 'delete the kitchen')")
    parser.add_argument(
        "--layout",
        default=None,
        help="Layout name to load e.g. industrial_005",
    )
    args = parser.parse_args()

    # Initialize and run the agent
    ctx = bootstrap()
    try:
        response = run_agent(args.prompt, ctx)

        # Print the final response
        print("\nAgent response:\n")
        safe_response = response.encode("ascii", errors="replace").decode("ascii")
        print(safe_response)
    finally:
        # Always close MCP client, even if run_agent crashes
        ctx.mcp_client.close()


if __name__ == "__main__":
    main()
