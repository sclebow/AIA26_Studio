from __future__ import annotations

import json
from typing import Any, Callable


SYSTEM_PROMPT = """You are a tool-using assistant.
You can either answer directly or request one MCP tool call.

Available tools:
{tool_catalog}

Return strictly valid JSON with exactly this shape:
{{
  \"action\": \"final\" | \"tool\",
  \"final_response\": \"...\",
  \"tool_calls\": [{{\"name\": \"<tool-name>\", \"arguments\": {{...}}}}, ...]
}}
Output rules:
- Return JSON only, with no prose or explanation.
- Do not use markdown code fences.
- Do not use XML tags like <function_calls>.
- Do not include any text before or after the JSON object.
- Do not include flags such as ```json or ```python.
- If action is \"final\", set tool_calls to [] and put the answer in final_response.
- If action is \"tool\", set final_response to \"\" and put one or more tool calls in tool_calls.
"""


def _strip_markdown_code_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) < 3:
        return stripped
    if not lines[-1].strip().startswith("```"):
        return stripped

    return "\n".join(lines[1:-1]).strip()


def _normalize_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        chunks: list[str] = []
        for block in content:
            if isinstance(block, str):
                chunks.append(block)
                continue
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks)

    return str(content)


def _parse_llm_json(content: str) -> dict[str, Any]:
    content = _strip_markdown_code_fence(content)
    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise RuntimeError("LLM JSON response must be an object")
        return parsed
    except json.JSONDecodeError as exc:
        if "Extra data" not in str(exc):
            raise

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("LLM response was empty")

    tool_calls: list[dict[str, Any]] = []
    for line in lines:
        parsed_line = json.loads(line)
        if not isinstance(parsed_line, dict):
            raise RuntimeError("Each JSON line must be an object")
        tool_call = parsed_line.get("tool_call")
        if not isinstance(tool_call, dict):
            raise RuntimeError("Each JSON line must contain 'tool_call'")
        tool_calls.append(tool_call)

    return {"tool_calls": tool_calls}


def _normalize_llm_decision(parsed: dict[str, Any]) -> dict[str, Any]:
    action = parsed.get("action")
    if action == "final":
        return {
            "action": "final",
            "final_response": parsed["final_response"],
        }

    if action == "tool":
        tool_calls = parsed.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            raise RuntimeError("LLM tool decision must include a non-empty 'tool_calls' array")

        normalized_tool_calls: list[dict[str, Any]] = []
        for tool in tool_calls:
            if not isinstance(tool, dict):
                raise RuntimeError("Each tool call must be an object")
            normalized_tool_calls.append(
                {
                    "tool_name": tool["name"],
                    "arguments": tool["arguments"],
                }
            )
        return {
            "action": "tool",
            "tool_calls": normalized_tool_calls,
        }

    if "final_response" in parsed:
        return {
            "action": "final",
            "final_response": parsed["final_response"],
        }

    tool_call = parsed.get("tool_call")
    if isinstance(tool_call, dict):
        return {
            "action": "tool",
            "tool_calls": [
                {
                    "tool_name": tool_call["name"],
                    "arguments": tool_call["arguments"],
                }
            ],
        }

    tool_calls = parsed.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        normalized_tool_calls: list[dict[str, Any]] = []
        for tool in tool_calls:
            if not isinstance(tool, dict):
                raise RuntimeError("Each tool call must be an object")
            normalized_tool_calls.append(
                {
                    "tool_name": tool["name"],
                    "arguments": tool["arguments"],
                }
            )
        return {
            "action": "tool",
            "tool_calls": normalized_tool_calls,
        }

    raise RuntimeError("LLM response must include either 'final_response' or 'tool_call'")


def create_reason_node(llm: Any, dbg: Callable[[str], None]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def reason_node(state: dict[str, Any]) -> dict[str, Any]:
        dbg(f"[graph][reason] Enter node | iteration={state['iteration']} | messages={len(state['messages'])}")
        system_prompt = SYSTEM_PROMPT.format(tool_catalog=state["tool_catalog"])
        llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}] + state["messages"]

        result = llm.invoke(llm_messages)
        content = _normalize_content_text(result.content)
        if not content.strip():
            # Keep the workflow alive when a local model returns an empty body.
            state["final_response"] = "I could not produce a model response for this step."
            state["pending_tool_calls"] = None
            dbg("[graph][reason] Empty model output; fallback decision=final")
            return state

        try:
            parsed = _normalize_llm_decision(_parse_llm_json(content))
        except Exception:
            print("\n[graph][reason] Raw LLM response before crash:")
            print(content)
            state["final_response"] = content.strip()
            state["pending_tool_calls"] = None
            dbg("[graph][reason] Non-JSON output; fallback decision=final")
            return state
        dbg(f"[graph][reason] Parsed decision: {parsed}")

        action = parsed["action"]
        if action == "final":
            final_response = parsed["final_response"]

            state["final_response"] = final_response
            state["pending_tool_calls"] = None
            dbg("[graph][reason] Decision=final")
            return state

        if action == "tool":
            tool_calls = parsed["tool_calls"]
            state["pending_tool_calls"] = tool_calls
            dbg(f"[graph][reason] Decision=tool | tool_calls={tool_calls}")
            return state

        raise RuntimeError("LLM action must be either 'final' or 'tool'")

    return reason_node
