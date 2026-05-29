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

import json
import re
from pathlib import Path
from _runtime.bootstrap import bootstrap
from graph import run_agent


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

# Path to the saved persona file (one level above python/)
_PERSONA_PATH = Path(__file__).resolve().parent.parent / "persona.json"


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


def main() -> None:
    print(_WELCOME)

    # Bootstrap once — MCP connection stays open for the whole session
    ctx = bootstrap()

    # ── Session initialisation ────────────────────────────────────────────────
    # Check for an existing persona.json; if found, skip onboarding entirely.
    existing_persona = _load_existing_persona()
    if existing_persona:
        session: dict = {
            "onboarding_complete": True,
            "greeted":             True,
            "quiz_complete":       True,
            "inspire_complete":    True,
            "persona_profile":     existing_persona,
            "user_type":           existing_persona.get("role", "client"),
        }
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
