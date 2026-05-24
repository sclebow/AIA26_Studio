"""
nodes/ask_persona.py — ASK_PERSONA node for the Comfort Copilot state graph.

Pure Python — no LLM, no MCP calls. Runs after LOAD_LAYOUT on the comfort path,
but only when no persona was detected in the user's prompt.

Responsibilities:
  Show an interactive terminal picker listing all available personas with
  descriptions, prompt the user to choose one by number, and write the
  selection to state.

Writes to state:
  persona_detected  (str)   — chosen persona name (e.g. "Elderly 65+")
  needs_persona_ask (bool)  — set to False after selection
"""

from __future__ import annotations
from personas import PERSONAS


def ask_persona_node(state: dict) -> dict:
    """
    If a persona is already known, pass through. Otherwise run the picker.
    """

    # ── Pass-through if persona already set ──────────────────────────────
    if state.get("persona_detected"):
        print(f"[ask_persona] Persona already set: {state['persona_detected']}")
        return state

    # ── Interactive picker ────────────────────────────────────────────────
    persona_names = list(PERSONAS.keys())

    print("\nWho is this layout for? Available personas:")
    for i, name in enumerate(persona_names, 1):
        desc = PERSONAS[name]["description"]
        print(f"  {i}. {name}")
        print(f"     {desc}")

    while True:
        try:
            choice = input("\nSelect a persona (enter number): ").strip()
            index = int(choice) - 1
            if 0 <= index < len(persona_names):
                selected = persona_names[index]
                print(f"Persona: {selected}\n")
                break
            print(f"Please enter a number between 1 and {len(persona_names)}")
        except ValueError:
            print("Invalid input. Please enter a number.")

    return {
        **state,
        "persona_detected":  selected,
        "needs_persona_ask": False,
    }
