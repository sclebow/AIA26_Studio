"""
AIA Studio Cost Advisor — Team 05 CLI
Interactive REPL + single-shot mode for orchestrating the cost agent.

Usage:
  python cli.py                              # interactive, no layout
  python cli.py --file layout.json           # interactive with layout pre-loaded
  python cli.py --file layout.json --input "What is the total cost?"  # single-shot
  python cli.py --agent team_01 --input "..."  # route to another team's agent stub
"""

import argparse
import json
import sys
from pathlib import Path

from langgraph_agent import LangGraphAgent

BANNER = """
╔══════════════════════════════════════════════════════╗
║   AIA Studio · Cost Advisor Agent · Team 05          ║
╚══════════════════════════════════════════════════════╝
 Commands:
   /load <path>   – load (or reload) a layout JSON file
   /layout        – print a summary of the current layout
   /rooms         – list all rooms and their costs
   /clear         – clear the conversation history
   /exit or /quit – quit
"""


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def load_layout(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"  [error] File not found: {path}")
    except json.JSONDecodeError as exc:
        print(f"  [error] Invalid JSON: {exc}")
    return None


def layout_summary(layout: dict) -> str:
    proj = layout.get("project", {})
    rooms = layout.get("rooms", [])
    currency = proj.get("currency", "")
    total = sum(r.get("total_cost", 0) for r in rooms)
    lines = [
        f"  Project : {proj.get('name', 'Unknown')}",
        f"  Currency: {currency}  |  Units: {proj.get('units', '?')}",
        f"  Footprint: {proj.get('footprint_m2', 0):.0f} m²",
        f"  Rooms   : {len(rooms)}  |  Total cost: {total:,.0f} {currency}",
    ]
    return "\n".join(lines)


def rooms_table(layout: dict) -> str:
    rooms = layout.get("rooms", [])
    currency = layout.get("project", {}).get("currency", "")
    header = f"  {'Room':<22} {'Area':>8}   {'Rate':>10}   {'Cost':>14}"
    sep = "  " + "-" * 62
    lines = [header, sep]
    for r in rooms:
        lines.append(
            f"  {r.get('name', ''):<22} "
            f"{r.get('area_m2', 0):>6.1f} m²  "
            f"{r.get('rate_per_m2', 0):>8,.0f} {currency}/m²  "
            f"{r.get('total_cost', 0):>10,.0f} {currency}"
        )
    total = sum(r.get("total_cost", 0) for r in rooms)
    lines += [sep, f"  {'TOTAL':<22} {'':>8}   {'':>10}   {total:>10,.0f} {currency}"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestrator: routes to sub-agent stubs for other teams
# ---------------------------------------------------------------------------

TEAM_STUBS: dict[str, str] = {
    "team_01": "Team 01 agent (structure / slabs)",
    "team_02": "Team 02 agent (MEP / services)",
    "team_03": "Team 03 agent (facades / envelope)",
    "team_04": "Team 04 agent (landscape / site)",
    "team_05": "Team 05 agent (cost advisor)",  # this team
}


def orchestrate(team: str, user_input: str, layout: dict | None, history: list[dict]) -> str:
    if team == "team_05":
        agent = LangGraphAgent()
        return agent.process(user_input, layout=layout, history=history)
    # Stub responses for other teams until their APIs are wired up.
    stub = TEAM_STUBS.get(team, f"Unknown team: {team}")
    return f"[Orchestrator → {stub}]\n  (Sub-agent not yet connected. Input forwarded: {user_input!r})"


# ---------------------------------------------------------------------------
# Interactive REPL
# ---------------------------------------------------------------------------

def run_interactive(team: str, layout: dict | None) -> None:
    print(BANNER)
    if layout:
        print("  Layout loaded:")
        print(layout_summary(layout))
        print()

    history: list[dict] = []

    while True:
        try:
            raw = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not raw:
            continue

        # ── built-in commands ────────────────────────────────────────────
        if raw.lower() in ("/exit", "/quit", "exit", "quit"):
            print("Bye.")
            break

        if raw.lower().startswith("/load "):
            path = raw[6:].strip()
            loaded = load_layout(path)
            if loaded is not None:
                layout = loaded
                history = []
                print(f"  Layout reloaded from {path}")
                print(layout_summary(layout))
            continue

        if raw.lower() == "/layout":
            if layout:
                print(layout_summary(layout))
            else:
                print("  No layout loaded. Use /load <path>")
            continue

        if raw.lower() == "/rooms":
            if layout:
                print(rooms_table(layout))
            else:
                print("  No layout loaded. Use /load <path>")
            continue

        if raw.lower() == "/clear":
            history = []
            print("  Conversation history cleared.")
            continue

        # ── agent call ───────────────────────────────────────────────────
        response = orchestrate(team, raw, layout, history)
        print(f"\nAgent: {response}\n")
        history.append({"role": "user", "content": raw})
        history.append({"role": "assistant", "content": response})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="AIA Studio Cost Advisor — Team 05 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python cli.py --file layout.json\n"
            "  python cli.py --file layout.json --input 'What is the total cost?'\n"
            "  python cli.py --agent team_02 --input 'What are the MEP costs?'\n"
        ),
    )
    parser.add_argument(
        "--file", "-f", metavar="PATH",
        help="Path to layout JSON file",
    )
    parser.add_argument(
        "--input", "-i", metavar="TEXT",
        help="Single instruction (non-interactive mode)",
    )
    parser.add_argument(
        "--agent", "-a", metavar="TEAM",
        choices=list(TEAM_STUBS.keys()),
        default="team_05",
        help="Target agent team (default: team_05)",
    )
    args = parser.parse_args()

    layout: dict | None = None
    if args.file:
        layout = load_layout(args.file)
        if layout is None:
            sys.exit(1)

    if args.input:
        response = orchestrate(args.agent, args.input, layout, [])
        print(response)
    else:
        run_interactive(args.agent, layout)


if __name__ == "__main__":
    main()
