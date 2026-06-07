from __future__ import annotations
from copy import deepcopy
import json
import os
import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# LLM factory — supports local (OpenAI-compatible) and Anthropic
# ---------------------------------------------------------------------------

def create_chat_llm(
    api_key: str,
    base_url: str,
    llm_model: str,
    timeout_seconds: float,
    model_kwargs: dict[str, Any] | None = None,
) -> Any:
    provider = os.environ.get("LLM_PROVIDER", "local").strip().lower()

    # Anthropic — use SDK directly, not LangChain
    # Returns a plain dict instead of a ChatOpenAI instance.
    # call_llm() detects this and routes to _call_anthropic().
    if provider == "anthropic":
        import anthropic
        return {
            "_type": "anthropic",
            "_client": anthropic.Anthropic(api_key=api_key),
            "_model": llm_model,
            "_timeout": timeout_seconds,
        }

    # All other providers — use LangChain OpenAI-compatible wrapper
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=llm_model,
        timeout=timeout_seconds,
        temperature=0,
        model_kwargs=model_kwargs or {},
    )


# ---------------------------------------------------------------------------
# Structured-output schema builders — used for local/OpenAI providers only
# For Anthropic, we use prompt-based JSON instead — no schema needed.
# ---------------------------------------------------------------------------

LLM_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["final", "tool"],
        },
        "final_response": {
            "type": "string",
            "description": "Use a non-empty string only when action is 'final'. Use an empty string when action is 'tool'.",
        },
        "tool_calls": {
            "type": "array",
            "description": "Use one or more tool calls only when action is 'tool'. Use an empty array when action is 'final'.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "arguments": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                },
                "required": ["name", "arguments"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["action", "final_response", "tool_calls"],
    "additionalProperties": False,
}


def _build_arguments_schema(tools: list[dict[str, Any]]) -> dict[str, Any]:
    merged_properties: dict[str, Any] = {}
    for tool in tools:
        input_schema = tool.get("inputSchema")
        if not isinstance(input_schema, dict):
            continue
        properties = input_schema.get("properties")
        if not isinstance(properties, dict):
            continue
        for property_name, property_schema in properties.items():
            if property_name in merged_properties:
                continue
            if not isinstance(property_schema, dict):
                continue
            nullable_schema = dict(property_schema)
            property_type = nullable_schema.get("type")
            if isinstance(property_type, str):
                nullable_schema["type"] = [property_type, "null"]
            merged_properties[property_name] = nullable_schema

    return {
        "type": "object",
        "properties": merged_properties,
        "required": list(merged_properties.keys()),
        "additionalProperties": False,
    }


def get_llm_response_format(tools: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Returns model_kwargs for structured output.
    For Anthropic — returns empty dict (handled via prompt, not response_format).
    For local/OpenAI — returns JSON schema response format.
    """
    provider = os.environ.get("LLM_PROVIDER", "local").strip().lower()

    if provider == "anthropic":
        return {}

    schema = deepcopy(LLM_DECISION_SCHEMA)
    tool_names = [str(tool.get("name")) for tool in tools if tool.get("name")]
    tool_call_schema = schema["properties"]["tool_calls"]["items"]
    tool_call_schema["properties"]["name"]["enum"] = tool_names
    tool_call_schema["properties"]["arguments"] = _build_arguments_schema(tools)

    return {
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "agent_decision",
                "strict": True,
                "schema": schema,
            },
        }
    }


# ---------------------------------------------------------------------------
# LLM response parsing helpers
# ---------------------------------------------------------------------------

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


def _parse_llm_json(content: str) -> dict[str, Any]:
    content_stripped = content.strip()

    # Handle Claude's <function_calls> XML format
    if "<function_calls>" in content_stripped:
        match = re.search(r'<function_calls>(.*?)</function_calls>', content_stripped, re.DOTALL)
        if match:
            calls_text = match.group(1).strip()
            try:
                calls = json.loads(calls_text)
                if isinstance(calls, list):
                    return {
                        "action": "tool",
                        "final_response": "",
                        "tool_calls": [
                            {
                                "name": c["name"],
                                "arguments": c.get("arguments", c.get("parameters", {}))
                            }
                            for c in calls
                        ]
                    }
            except json.JSONDecodeError:
                pass

    # Extract JSON from ```json ... ``` fence anywhere in content
    fence_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', content_stripped, re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Find raw JSON object anywhere in content
    json_match = re.search(r'\{.*\}', content_stripped, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Try direct parse — pure JSON response with no surrounding text
    try:
        parsed = json.loads(_strip_markdown_code_fence(content_stripped))
        if not isinstance(parsed, dict):
            raise RuntimeError("LLM JSON response must be an object")
        return parsed
    except json.JSONDecodeError:
        pass

    raise RuntimeError(
        "Could not extract JSON from LLM response: {}".format(content_stripped[:200])
    )


def _extract_tool_name(t: dict) -> str:
    """Extract tool name from a tool call dict, handling LLM format variations."""
    return t.get("name") or t.get("tool_name") or t.get("function", "")


def _normalize_tool_calls(raw_calls: list) -> list[dict]:
    """Normalize a list of tool call dicts to [{name, arguments}, ...]."""
    return [
        {"name": _extract_tool_name(t), "arguments": t.get("arguments", t.get("input", {}))}
        for t in raw_calls
        if _extract_tool_name(t)
    ]


def _normalize_llm_decision(parsed: dict[str, Any]) -> dict[str, Any]:
    action = parsed.get("action")

    if action == "query":
        return {"action": "query"}

    if action == "final":
        return {"action": "final", "final_response": parsed["final_response"]}

    if action == "tool":
        tool_calls = parsed.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            raise RuntimeError("LLM tool decision must include a non-empty 'tool_calls' array")
        return {"action": "tool", "tool_calls": _normalize_tool_calls(tool_calls)}

    if "final_response" in parsed:
        return {"action": "final", "final_response": parsed["final_response"]}

    tool_call = parsed.get("tool_call")
    if isinstance(tool_call, dict):
        return {
            "action": "tool",
            "tool_calls": [{"name": _extract_tool_name(tool_call), "arguments": tool_call.get("arguments", tool_call.get("input", {}))}],
        }

    tool_calls = parsed.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        return {"action": "tool", "tool_calls": _normalize_tool_calls(tool_calls)}

    raise RuntimeError("LLM response must include either 'final_response' or 'tool_call'")


# ---------------------------------------------------------------------------
# Anthropic-specific call — bypasses LangChain entirely
# ---------------------------------------------------------------------------

def _call_anthropic(
    client_dict: dict,
    system_prompt: str,
    messages: list[dict[str, str]],
    tool_catalog: str,
) -> dict[str, Any]:
    client  = client_dict["_client"]
    model   = client_dict["_model"]
    timeout = client_dict["_timeout"]

    # Use replace() instead of .format() — the prompt may contain literal
    # braces from JSON content that .format() would choke on.
    formatted_prompt = system_prompt.replace("{tool_catalog}", tool_catalog)

    # Anthropic only accepts "user" and "assistant" roles.
    # Handle both plain dicts and LangChain message objects (HumanMessage, etc.)
    # since the add_messages reducer may convert dicts to message objects.
    anthropic_messages = []
    for msg in messages:
        if isinstance(msg, dict):
            role    = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role    = getattr(msg, "type", "user")
            content = getattr(msg, "content", "")
        if role == "system":
            continue
        if role == "human":
            role = "user"
        elif role == "ai":
            role = "assistant"
        anthropic_messages.append({"role": role, "content": content})

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=formatted_prompt,
        messages=anthropic_messages,
        timeout=timeout,
    )

    content = response.content[0].text
    print("\n[anthropic] Raw response preview:")
    print(content[:400])

    return _normalize_llm_decision(_parse_llm_json(content))


# ---------------------------------------------------------------------------
# Public convenience function used by reason nodes
# ---------------------------------------------------------------------------

def call_llm(
    llm: Any,
    system_prompt: str,
    messages: list[dict[str, str]],
    tool_catalog: str,
) -> dict[str, Any]:
    """Invoke the LLM and return a parsed decision dict.
    Handles both Anthropic and local/OpenAI providers.
    """
    # Anthropic path — use SDK directly
    if isinstance(llm, dict) and llm.get("_type") == "anthropic":
        return _call_anthropic(llm, system_prompt, messages, tool_catalog)

    # Local / OpenAI / Cloudflare path — use LangChain
    formatted_prompt = system_prompt.replace("{tool_catalog}", tool_catalog)
    llm_messages = [{"role": "system", "content": formatted_prompt}] + messages

    result = llm.invoke(llm_messages)
    content = result.content
    if not isinstance(content, str):
        raise RuntimeError("LLM response content must be a string")

    try:
        return _normalize_llm_decision(_parse_llm_json(content))
    except Exception:
        print("\n[llm] Raw LLM response before crash:")
        print(content)
        raise


def call_llm_simple(
    llm: Any,
    system_prompt: str,
    user_message: str,
) -> dict[str, Any] | None:
    """
    Simplified LLM call for pre-agent nodes
    (profile_agent, space_type_agent).
    No tool_catalog needed — returns parsed
    JSON dict or None on failure.
    Unlike call_llm(), no action/tool_calls
    schema is expected — just free-form JSON.
    """
    try:
        # Anthropic path — call API directly and parse as free-form JSON.
        # Do NOT route through _call_anthropic / _normalize_llm_decision
        # because pre-agents return free-form JSON (e.g. {"profile_type": ...}),
        # not the {"action": "final", "tool_calls": [...]} schema that
        # _normalize_llm_decision expects.
        # Retries up to 3 times on transient errors (529 overloaded, timeouts).
        if isinstance(llm, dict) and llm.get("_type") == "anthropic":
            import time as _time
            client  = llm["_client"]
            model   = llm["_model"]
            timeout = llm["_timeout"]
            _max_retries = 3
            response = None
            for _attempt in range(1, _max_retries + 1):
                try:
                    response = client.messages.create(
                        model=model,
                        max_tokens=4096,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_message}],
                        timeout=timeout,
                    )
                    break
                except Exception as _retry_exc:
                    print(f"[llm_simple] Failed: {_retry_exc}")
                    if _attempt < _max_retries:
                        _wait = _attempt * 5
                        print(f"[llm_simple] Retrying in {_wait}s...")
                        _time.sleep(_wait)
                    else:
                        raise
            content = response.content[0].text
            print(f"\n[llm_simple] Raw response preview:\n{content[:400]}")
            cleaned = _strip_markdown_code_fence(content)
            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                return parsed if isinstance(parsed, dict) else None
            return None

        # Local/OpenAI path — invoke via LangChain
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ]
        result = llm.invoke(messages)
        content = result.content
        if not isinstance(content, str):
            return None
        cleaned = _strip_markdown_code_fence(content)
        parsed  = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None

    except Exception as exc:
        print(f"[llm_simple] Failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Tool output persistence helper used by tool nodes
# ---------------------------------------------------------------------------

def write_tool_result(tool_output: str, path: Path) -> None:
    """Write the MCP tool output to a file, pretty-printing JSON if possible."""
    stripped = tool_output.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        text = tool_output if tool_output.endswith("\n") else tool_output + "\n"
    else:
        text = json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")