"""
GREET node — first turn only.
Sends a single warm opening line: "Hi, I'm Sensi — who are you?"
Does NOT classify the user; that is USER_PROFILER's job on the next turn.
"""

from __future__ import annotations
from _runtime.llm import call_llm_simple


_SYSTEM_PROMPT = """\
You are Sensi, a sensorial comfort companion for apartment layouts.

This is the very first message. Your only job right now is to say hello and ask
who the user is. Keep it to one single line, warm and casual:

  "Hi, I'm Sensi — who are you?"

That's it. No features list, no explanations, no questions about layouts yet.
Just the greeting. If the user already introduced themselves in their message,
skip the question and just say "Nice to meet you, [name]!" — still one line.
"""


def build_greet_node(llm):
    """Return the greet node function, capturing the LLM instance."""

    def greet_node(state: dict) -> dict:
        raw_prompt: str = state.get("raw_prompt", "")

        print("[greet] Generating opening message...")
        response = call_llm_simple(llm, _SYSTEM_PROMPT, raw_prompt or "Hello")

        return {
            **state,
            "greeted": True,
            "final_response": response,
        }

    return greet_node
