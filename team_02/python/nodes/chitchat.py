"""
nodes/chitchat.py — CHITCHAT node for the Comfort Copilot state graph.

LLM node. Handles any prompt that didn't trigger the comfort or inspire path —
general questions, greetings, domain knowledge queries, and anything else.

Reads from state:
  raw_prompt  (str)  — original user message

Writes to state:
  final_response  (str)  — conversational reply
"""

from __future__ import annotations
from _runtime.llm import call_llm_simple


_SYSTEM_PROMPT = """\
You are Comfort Copilot, an expert in multi-sensory architectural comfort.
Your six dimensions of analysis are: thermal, visual, acoustic, spatial,
olfactory, and tactile comfort.

Answer the user's question clearly and helpfully. If they are asking about
comfort concepts, explain them in plain language with concrete architectural
examples. If they are asking something unrelated to architecture or comfort,
answer politely and briefly, then gently guide them back to what you can help
with most: analysing apartment layouts for sensory wellbeing.

If the user wants to start an analysis, let them know they can mention a
layout number (201, 202, or 203) in their message and you will load it
automatically.

Keep your response concise — no more than a short paragraph or two.
"""


def build_chitchat_node(llm):
    """Return the chitchat node function, capturing the LLM instance."""

    def chitchat_node(state: dict) -> dict:
        raw_prompt: str = state.get("raw_prompt", "")

        print(f"[chitchat] Generating conversational response...")
        response = call_llm_simple(llm, _SYSTEM_PROMPT, raw_prompt)

        return {
            **state,
            "final_response": response,
        }

    return chitchat_node
