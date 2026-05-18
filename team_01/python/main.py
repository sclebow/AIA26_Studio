import argparse
from _runtime.bootstrap import bootstrap
from graph import run_agent


def main():

    # Process the command line arguments (the user instruction)
    # Receive the argunment with a prompt for the agent, e.g. "delete the kitchen"
    parser = argparse.ArgumentParser(description="Run the Grasshopper MCP agent.")
    parser.add_argument("prompt", help="Your instruction for the agent (e.g. 'delete the kitchen')")
    args = parser.parse_args()

    # Initialize and run the agent
    ctx = bootstrap()
    response = run_agent(args.prompt, ctx)

    # Print the final response
    print("\nAgent response:\n")
    safe_response = response.encode("ascii", errors="replace").decode("ascii")
    print(safe_response)

    # Clean up by properly closing the MCP client connection
    ctx.mcp_client.close()


if __name__ == "__main__":
    main()
