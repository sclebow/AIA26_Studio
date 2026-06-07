import argparse
import json
import sys
import os
from _runtime.bootstrap import bootstrap
from graph import run_agent

def main():
    # 1. Switch from a single positional argument to explicit flags
    parser = argparse.ArgumentParser(description="Run the Grasshopper MCP agent.")
    parser.add_argument("--prompt", required=True, help="Your instruction for the agent (e.g. 'delete the kitchen')")
    parser.add_argument("--layout_json", required=False, help="Optional JSON string of the layout")
    args = parser.parse_args()

    # 2. Parse layout_json when provided, exit safely on failure
    parsed_layout = None
    if args.layout_json:
        try:
            parsed_layout = json.loads(args.layout_json)
        except json.JSONDecodeError as e:
            print(f"Error parsing --layout_json: {e}", file=sys.stderr)
            sys.exit(1)

    # 3. Initialize context and override layout_data if CLI input was provided
    ctx = bootstrap()
    if parsed_layout is not None:
        ctx.layout_data = parsed_layout

    # (Optional helper) Track if the layout file gets modified during the run
    mod_time_before = os.path.getmtime(ctx.edited_layout_path) if ctx.edited_layout_path.exists() else 0

    # 4. Execute the graph with the parsed prompt
    response = run_agent(args.prompt, ctx)

    # Determine if the layout changed by checking if the MCP tools overwrote the layout file
    edited_layout_str = "No layout changes"
    if ctx.edited_layout_path.exists():
        mod_time_after = os.path.getmtime(ctx.edited_layout_path)
        if mod_time_after > mod_time_before:
            with open(ctx.edited_layout_path, "r", encoding="utf-8") as f:
                edited_layout_str = f.read()

    # 5. Print output using the exact machine-readable structure required by the orchestrator
    print("Final Response:")
    print(response)
    print("Edited Layout JSON:")
    print(edited_layout_str)

    # Clean up by properly closing the MCP client connection
    ctx.mcp_client.close()

if __name__ == "__main__":
    main()