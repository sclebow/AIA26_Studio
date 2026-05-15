"""
nodes/inspire.py — INSPIRE node for the Comfort Copilot state graph.

Placeholder for Phase 3 — atmosphere / image generation from layout data.
Currently returns a holding message so the graph path is complete and
testable without breaking anything.

Triggered when:
  - The user attaches an image, OR
  - The prompt contains atmosphere / mood / inspiration keywords

Reads from state:
  raw_prompt  (str)  — original user message

Writes to state:
  final_response  (str)  — placeholder message
"""

from __future__ import annotations


_PLACEHOLDER = (
    "The Inspire mode — atmosphere generation from layout and image — "
    "is coming in Phase 3. For now, try asking me to analyse a layout "
    "by mentioning its number (201, 202, or 203) in your message."
)


def inspire_node(state: dict) -> dict:
    print("[inspire] Inspire path triggered — returning placeholder.")
    return {
        **state,
        "final_response": _PLACEHOLDER,
    }
