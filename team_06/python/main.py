import argparse
import json
import sys


def _safe_text(value: str) -> str:
    return value.encode("ascii", errors="replace").decode("ascii")


def _format_layout_output(edited_layout_json: str | None) -> str:
    if not edited_layout_json:
        return "No layout changes"

    try:
        edited_layout = json.loads(edited_layout_json)
    except json.JSONDecodeError:
        return "No layout changes"

    if not isinstance(edited_layout, dict) or not edited_layout:
        return "No layout changes"

    return json.dumps(edited_layout, indent=2, ensure_ascii=True)


def _print_result(response: str, edited_layout_output: str, include_layout_json: bool) -> None:
    print("Final Response:", flush=True)
    print(_safe_text(response), flush=True)
    if include_layout_json:
        print("Edited Layout JSON:", flush=True)
        print(edited_layout_output, flush=True)


def _parse_layout_json(layout_json: str) -> dict:
    try:
        parsed = json.loads(layout_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid --layout_json: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Invalid --layout_json: expected a JSON object")

    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Grasshopper MCP agent.")
    parser.add_argument("--prompt", required=True, help="Instruction for the agent")
    parser.add_argument("--layout_json", help="Optional layout JSON object to override bootstrap layout")
    parser.add_argument("--hide_layout_json", action="store_true", help="Suppress Edited Layout JSON in CLI output")
    args = parser.parse_args()

    prompt_text = args.prompt
    layout_override = None
    if args.layout_json is not None:
        try:
            layout_override = _parse_layout_json(args.layout_json)
        except ValueError as exc:
            print(_safe_text(f"Error: {exc}"), file=sys.stderr)
            return 1

    from _runtime.bootstrap import bootstrap
    from graph import run_agent

    print("Status: Initializing agent runtime.", flush=True)
    ctx = bootstrap()

    try:
        if layout_override is not None:
            ctx.layout_data = layout_override

        session = {"feedback_history": []}
        next_prompt = prompt_text

        while True:
            response, session = run_agent(next_prompt, ctx, session)
            edited_layout_output = _format_layout_output(session.get("layout_json_string"))
            _print_result(response, edited_layout_output, include_layout_json=not args.hide_layout_json)

            if not sys.stdin.isatty() or not session.get("needs_user_input", False):
                break

            try:
                next_prompt = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not next_prompt:
                break

        return 0
    finally:
        ctx.mcp_client.close()


if __name__ == "__main__":
    sys.exit(main())