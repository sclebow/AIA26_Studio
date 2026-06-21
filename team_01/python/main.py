import argparse
import json
import sys
from _runtime.bootstrap import bootstrap
from graph import run_agent


def main():
    parser = argparse.ArgumentParser(description="Run the Permanence_OS structural agent.")
    parser.add_argument("--prompt", required=True, help="Instruction for the agent")
    parser.add_argument("--layout_json", default=None, help="Floor plan as a JSON string (optional)")
    args = parser.parse_args()

    layout_data = None
    if args.layout_json:
        try:
            layout_data = json.loads(args.layout_json)
        except json.JSONDecodeError as e:
            print(f"Error: --layout_json is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)

    ctx = bootstrap()
    response, edited_layout, app = run_agent(args.prompt, ctx, layout_data=layout_data)

    safe_response = response.encode("ascii", errors="replace").decode("ascii")
    print("\nFinal Response:")
    print(safe_response)
    print("\nEdited Layout JSON:")
    if edited_layout:
        print(edited_layout)
    else:
        print("No layout changes")

    print("\nWorkflow graph:")
    app.get_graph().print_ascii()

    try:
        ctx.mcp_client.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
