from __future__ import annotations
from typing import Any
from _runtime.llm import call_llm


# ---------------------------------------------------------------------------
# System prompt — edit this to change how the agent thinks and behaves.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an assistant that helps users work with a building layout.

The MCP tools listed below are a toolbox: you may call them when they help achieve the user's goal. Choose tools and arguments only based on the user's request, the tool descriptions, and each tool's inputSchema. Do not assume any particular tool is required for a given instruction.

Always ground your reasoning in the current layout JSON shown in the user message. That payload is loaded from the repository's layout_input/layout_schema.json and defines the structure, attribute names, ids, and nested objects you should use for context (for example which keys exist, how entities reference each other, and what values are valid to mention or pass through).

If the user's goal cannot be satisfied without information that is missing from their message or from that layout JSON, respond with action "final" and ask a concise clarifying question.

After a tool result appears in the conversation, decide whether another tool call is needed or whether to respond with action "final" (for example to confirm completion or summarize what happened, including any output path or details echoed from the tool result when relevant).

Toolbox (name, description, and inputSchema for each tool):
{tool_catalog}

Return strictly valid JSON with exactly this shape:
{{
  "action": "final" | "tool",
  "final_response": "...",
  "tool_calls": [{{"name": "<tool-name>", "arguments": {{...}}}}, ...]
}}

Output rules:
- Return JSON only, with no prose or explanation.
- Do not use markdown code fences.
- If action is "final", set tool_calls to [] and put the answer in final_response.
- If action is "tool", set final_response to "" and put one or more tool calls in tool_calls.
"""


# ---------------------------------------------------------------------------
# Reason node — the LLM decision step in the graph.
# ---------------------------------------------------------------------------

def build_reason_node(llm):
    """Return a reason node function ready to be added to a LangGraph StateGraph."""

    def reason_node(state):
        result = call_llm(llm, SYSTEM_PROMPT, state["messages"], state["tool_catalog"])

        # If the LLM decided no more actions are needed (action is final), set the final response in the state and clear pending tool calls
        if result["action"] == "final":
            state["final_response"] = result["final_response"]
            state["pending_tool_calls"] = None

        # If the LLM decided the action is to use a tool, set the pending tool calls
        else:
            state["pending_tool_calls"] = result["tool_calls"]

        return state

    return reason_node
