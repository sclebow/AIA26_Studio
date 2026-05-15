from __future__ import annotations
from typing import Any
from _runtime.llm import call_llm
import time

SYSTEM_PROMPT = """You are a structural memory assistant helping an architect make early design decisions without a structural engineer.

Your job is to make the consequences of infrastructure decisions legible before they become irreversible. You do not design. You do not calculate loads.

You classify elements, score refurbishment cost, flag conflicts, and explain consequences in plain language. Use element IDs and attributes exactly as given. Do not invent elements, dimensions, or structural assumptions.

When multiple layouts exist, call the tool once per layout, passing each layout's JSON individually. Do not skip any layout.

If information is missing, respond with action "final" and ask one clarifying question.
After a tool result, decide if another tool call is needed or respond with action "final" to summarize.

Tools:
{tool_catalog}

Response format:
{{
  "action": "final" | "tool",
  "final_response": "...",
  "tool_calls": [{{"name": "<tool>", "arguments": {{...}}}}]
}}

Return JSON only. No markdown. No prose.
If final: tool_calls=[]. If tool: final_response="".
"""

def build_reason_node(llm):

    def reason_node(state):
        print("\nReasoning with LLM...")

        result = None
        last_error = None

        for attempt in range(3):
            try:
                result = call_llm(llm, SYSTEM_PROMPT, state["messages"], state["tool_catalog"])
                break
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    print(f"LLM call failed (attempt {attempt+1}/3), retrying in {wait}s... {e}")
                    time.sleep(wait)

        if result is None:
            raise RuntimeError(f"LLM failed after 3 attempts: {last_error}")

        if result["action"] == "final":
            state["final_response"] = result["final_response"]
            state["pending_tool_calls"] = None
        else:
            state["pending_tool_calls"] = result["tool_calls"]

        return state

    return reason_node