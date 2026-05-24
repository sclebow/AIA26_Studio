"""
main.py — Comfort Copilot entry point.

The while loop here IS the idle state. The agent stays alive between turns,
carrying layout and persona across the conversation.

Commands:
  exit / quit  → close MCP connection and end the session
  reset        → clear the loaded layout and persona, start fresh
  <anything>   → run one turn of the agent graph
"""

from _runtime.bootstrap import bootstrap
from graph import run_agent


_WELCOME = """
+------------------------------------------------------+
|          COMFORT COPILOT  -  Sensorial Atmos         |
|  Multi-sensory comfort analysis for apartment        |
|  layouts across thermal, visual, acoustic,           |
|  spatial, olfactory, and tactile dimensions.         |
+------------------------------------------------------+
|  Mention a layout number (201, 202, 203) to start.   |
|  Type  reset  to clear layout / persona.             |
|  Type  exit   to quit.                               |
+------------------------------------------------------+
"""


def _print_session_status(session: dict) -> None:
    """Print a compact one-line summary of what is loaded in the session."""
    layout_id = session.get("layout_id")
    persona   = session.get("persona_detected")
    parts = []
    if layout_id:
        parts.append(f"layout {layout_id}")
    if persona:
        parts.append(f"persona: {persona}")
    if parts:
        print(f"[session] {' | '.join(parts)}")


def main() -> None:
    print(_WELCOME)

    # Bootstrap once — MCP connection stays open for the whole session
    ctx = bootstrap()

    # Session carries layout and persona across turns
    session: dict = {}

    while True:

        # ── Status + prompt ───────────────────────────────────────────────
        _print_session_status(session)
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue

        # ── Commands ──────────────────────────────────────────────────────
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye.")
            break

        if user_input.lower() == "reset":
            session = {}
            print("[session] Cleared -- layout and persona reset.")
            continue

        # ── Run one turn of the agent graph ───────────────────────────────
        try:
            response, session = run_agent(user_input, ctx, session)
        except Exception as exc:
            print(f"\n[error] Something went wrong: {exc}")
            print("The session is still active. Try again or type 'reset'.")
            continue

        # ── Print response ────────────────────────────────────────────────
        print("\nComfort Copilot:\n")
        # Replace common Unicode punctuation with ASCII equivalents before
        # encoding, so Windows terminals don't show ? for em dashes etc.
        safe_response = (
            response
            .replace("—", " - ")   # em dash
            .replace("–", " - ")   # en dash
            .replace("’", "'")     # right single quote
            .replace("‘", "'")     # left single quote
            .replace("“", '"')     # left double quote
            .replace("”", '"')     # right double quote
            .replace("•", "-")     # bullet
            .replace("é", "e")     # é
            .replace("è", "e")     # è
        )
        safe_response = safe_response.encode("ascii", errors="replace").decode("ascii")
        print(safe_response)
        print()

    # ── Cleanup ───────────────────────────────────────────────────────────
    ctx.mcp_client.close()


if __name__ == "__main__":
    main()
