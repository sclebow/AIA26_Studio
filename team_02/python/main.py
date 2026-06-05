"""
main.py - Sensi entry point.

The while loop here IS the idle state. The agent stays alive between turns,
carrying layout and persona across the conversation.

RETURNING USERS:
  If team_02/persona.json exists, it is loaded at startup and the onboarding
  flow (greet → quiz → inspire → persona_compiler) is skipped entirely.
  The user lands directly in layout mode.

Commands:
  exit / quit / bye / goodbye  -> close and end the session
  reset                        -> clear session (keeps persona.json on disk)
  reset persona                -> delete persona.json and restart full onboarding
  <anything>                   -> run one turn of the agent graph
"""

import argparse
import contextlib
import json
import re
import sys
import tempfile
from pathlib import Path
from _runtime.bootstrap import bootstrap
from graph import run_agent
from nodes._shared.utils import layout_digits


def _clean_response(text: str) -> str:
    """Strip markdown formatting and normalize unicode for terminal display."""
    # Remove bold/italic markdown
    text = re.sub(r'\*+(.*?)\*+', r'\1', text)
    text = re.sub(r'_+(.*?)_+', r'\1', text)
    # Replace common unicode punctuation with ASCII equivalents
    text = text.replace('—', ' - ')   # em dash
    text = text.replace('–', ' - ')   # en dash
    text = text.replace('’', "'")     # right single quote
    text = text.replace('‘', "'")     # left single quote
    text = text.replace('“', '"')     # left double quote
    text = text.replace('”', '"')     # right double quote
    text = text.replace('•', '-')     # bullet
    text = text.replace('é', 'e')     # e acute
    text = text.replace('è', 'e')     # e grave
    # Replace any remaining non-ASCII with ?
    return text.encode('ascii', errors='replace').decode('ascii')


_WELCOME = """
+------------------------------------------------------+
|                  hi, i'm sensi :)                    |
|  your sensorial comfort companion for apartment      |
|  layouts -- thermal, visual, acoustic, spatial,      |
|  olfactory, and tactile comfort, all in one place.   |
+------------------------------------------------------+
|  Type  reset          to restart (keeps your profile)|
|  Type  reset persona  to delete profile and re-onboard|
|  Type  exit           to quit.                       |
+------------------------------------------------------+
"""

# Canonical persona location — must match where the graph writes it
# (graph.py: ctx.layout_input_dir.parent / "personas" / "persona.json") and where
# the web server reads it (api/server.py). Keeping these in sync prevents the CLI
# from "forgetting" a persona the graph just saved.
_PERSONA_PATH = Path(__file__).resolve().parent.parent / "personas" / "persona.json"


def _load_existing_persona() -> dict | None:
    """Return the saved persona dict if persona.json exists, else None."""
    if _PERSONA_PATH.exists():
        try:
            data = json.loads(_PERSONA_PATH.read_text(encoding="utf-8"))
            print(f"[session] Loaded existing persona: {data.get('name', 'User')} ({data.get('role', '?')})")
            return data
        except Exception as exc:
            print(f"[session] Could not read persona.json: {exc}")
    return None


def _print_session_status(session: dict) -> None:
    """Print a compact one-line summary of what is loaded in the session."""
    layout_id = session.get("layout_id")
    persona   = session.get("persona_profile")
    parts = []
    if layout_id:
        parts.append("layout {}".format(layout_id))
    if persona:
        parts.append("persona loaded")
    if parts:
        print("[session] {}".format(" | ".join(parts)))


def _completed_onboarding_session(persona: dict | None) -> dict:
    """Build a session that bypasses onboarding (greet/quiz/inspire) entirely.

    Used both by returning-user REPL launches and by headless CLI mode, where a
    subprocess cannot run the interactive onboarding flow.
    """
    return {
        "onboarding_complete": True,
        "greeted":             True,
        "quiz_complete":       True,
        "inspire_complete":    True,
        "persona_profile":     persona,
        "user_type":           (persona or {}).get("role", "client"),
    }


# ---------------------------------------------------------------------------
# Headless CLI mode (orchestrator subprocess)
# ---------------------------------------------------------------------------

def _print_cli_output(response: str, session: dict) -> None:
    """Print the stable, machine-readable block the orchestrator parses.

        Final Response:
        <agent response>

        Edited Layout JSON:
        <edited layout JSON or "No layout changes">
    """
    print("Final Response:")
    print(_clean_response(response or ""))
    print()
    print("Edited Layout JSON:")
    if session.get("layout_updated") and session.get("layout_json_string"):
        try:
            layout = json.loads(session["layout_json_string"])
            print(json.dumps(layout, indent=2, ensure_ascii=False))
        except (json.JSONDecodeError, TypeError):
            print("No layout changes")
    else:
        print("No layout changes")


def run_cli(ctx, prompt: str, layout_data: dict | None) -> None:
    """Run one orchestrator turn headlessly, then stay alive for stdin follow-ups.

    The first turn uses --prompt (and the optional --layout_json). After printing
    the machine-readable output block, the process keeps reading lines from stdin
    so the orchestrator can answer clarifying questions or continue the
    conversation. EOF / "exit" ends the process.
    """
    # Keep resulting_layout/ clean: redirect analysis writes to a throwaway dir so
    # orchestrator-supplied layouts (e.g. "Layout-101") never pollute the repo.
    ctx.layout_output_dir = Path(tempfile.mkdtemp(prefix="sensi_cli_"))

    # Skip onboarding — a subprocess can't run greet/quiz/inspire. Load persona if
    # one exists so scoring uses real comfort weights; otherwise neutral (None).
    # Diagnostics go to stderr so stdout carries ONLY the structured output block.
    with contextlib.redirect_stdout(sys.stderr):
        persona = _load_existing_persona()
    session = _completed_onboarding_session(persona)

    # Inject the orchestrator-provided layout straight into the session. The
    # load_layout node's skip-guard honors a pre-loaded matching layout instead of
    # reading from randomized_layouts/, so no graph changes are needed.
    if layout_data is not None:
        session["layout_json_string"] = json.dumps(layout_data)
        session["layout_id"]          = layout_digits(layout_data.get("layoutId"))

    def _turn(text: str) -> None:
        try:
            # Node/graph diagnostics print to stdout; redirect them to stderr so
            # only the structured block below reaches the orchestrator on stdout.
            with contextlib.redirect_stdout(sys.stderr):
                response, new_session = run_agent(text, ctx, session)
        except Exception as exc:
            print("Final Response:")
            print("[error] {}".format(exc))
            print()
            print("Edited Layout JSON:")
            print("No layout changes")
            return
        session.update(new_session)
        _print_cli_output(response, session)

    # First turn from --prompt
    _turn(prompt)

    # Stay alive for stdin follow-ups (clarifications / continued conversation).
    while True:
        try:
            user_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye", "goodbye"):
            break
        _turn(user_input)

    ctx.mcp_client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sensi - sensorial comfort agent for apartment layouts."
    )
    parser.add_argument(
        "--prompt", type=str, default=None,
        help="User instruction. When provided, runs in headless CLI mode "
             "(machine-readable output) instead of the interactive REPL.",
    )
    parser.add_argument(
        "--layout_json", type=str, default=None,
        help="Optional layout as a JSON string (orchestrator-provided). "
             "Only used together with --prompt.",
    )
    args = parser.parse_args()

    # ── Headless CLI mode (orchestrator subprocess) ────────────────────────────
    if args.prompt is not None:
        layout_data: dict | None = None
        if args.layout_json is not None:
            try:
                layout_data = json.loads(args.layout_json)
            except json.JSONDecodeError as exc:
                print("[error] --layout_json is not valid JSON: {}".format(exc),
                      file=sys.stderr)
                sys.exit(1)
            if not isinstance(layout_data, dict):
                print("[error] --layout_json must be a JSON object.", file=sys.stderr)
                sys.exit(1)
        # Bootstrap prints tool-discovery diagnostics — keep them off stdout.
        with contextlib.redirect_stdout(sys.stderr):
            ctx = bootstrap()
        run_cli(ctx, args.prompt, layout_data)
        return

    # ── Interactive REPL (default) ─────────────────────────────────────────────
    print(_WELCOME)

    # Bootstrap once — MCP connection stays open for the whole session
    ctx = bootstrap()

    # ── Session initialisation ────────────────────────────────────────────────
    # Check for an existing persona.json; if found, skip onboarding entirely.
    existing_persona = _load_existing_persona()
    if existing_persona:
        session: dict = _completed_onboarding_session(existing_persona)
        name = existing_persona.get("name", "")
        welcome_back = f"Welcome back{', ' + name if name else ''}! Your comfort profile is loaded. Tell me which layout you'd like to explore (201, 202, or 203)."
        print(f"\nSensi:\n\n{welcome_back}\n")
    else:
        session = {}
        # Auto-greet on first launch — run one silent turn so GREET fires
        try:
            response, session = run_agent("", ctx, session)
            print("\nSensi:\n")
            print(_clean_response(response))
            print()
        except Exception as exc:
            print("\n[error] Could not start greeting: {}".format(exc))

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:

        _print_session_status(session)
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue

        # Commands
        if user_input.lower() in ("exit", "quit", "bye", "goodbye"):
            print("\nSensi:\n")
            print("Bye! Come back when you have a layout to explore :)")
            break

        if user_input.lower() == "reset persona":
            if _PERSONA_PATH.exists():
                _PERSONA_PATH.unlink()
                print("[session] persona.json deleted — onboarding will restart.")
            session = {}
            try:
                response, session = run_agent("", ctx, session)
                print("\nSensi:\n")
                print(_clean_response(response))
                print()
            except Exception as exc:
                print("\n[error] Could not restart greeting: {}".format(exc))
            continue

        if user_input.lower() == "reset":
            # Clear layout/analysis state but keep onboarding flags and persona
            session = {
                k: v for k, v in session.items()
                if k in ("onboarding_complete", "greeted", "quiz_step", "quiz_answers",
                         "quiz_complete", "inspire_prompted", "inspire_summary",
                         "inspire_complete", "persona_profile", "user_type")
            }
            print("[session] Layout cleared — persona and onboarding state kept.")
            continue

        # Run one turn of the agent graph
        try:
            response, session = run_agent(user_input, ctx, session)
        except Exception as exc:
            print("\n[error] Something went wrong: {}".format(exc))
            print("The session is still active. Try again or type 'reset'.")
            continue

        print("\nSensi:\n")
        print(_clean_response(response))
        print()

    # Cleanup
    ctx.mcp_client.close()


if __name__ == "__main__":
    main()
