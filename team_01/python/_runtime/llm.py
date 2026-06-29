from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
from typing import Any
from langchain_openai import ChatOpenAI


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def create_chat_llm(
    api_key: str,
    base_url: str,
    llm_model: str,
    timeout_seconds: float,
    model_kwargs: dict[str, Any] | None = None,
    provider: str = "local",
) -> Any:
    """Build a LangChain chat model for the configured provider.

    provider="anthropic" -> ChatAnthropic (Claude). The agent invokes the LLM
    as plain text that it parses into JSON, so no provider-specific structured
    output binding is needed; we only need a generous max_tokens so the
    advisory text + tool-call JSON is never truncated.
    """
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            api_key=api_key,
            model=llm_model,
            timeout=timeout_seconds,
            temperature=0,
            max_tokens=4096,
        )

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=llm_model,
        timeout=timeout_seconds,
        temperature=0,
        model_kwargs=model_kwargs or {},
    )


# ---------------------------------------------------------------------------
# Structured-output schema builders
#
# get_llm_response_format() generates a provider-compatible JSON schema that
# constrains the LLM's output to a predictable shape for tool decisions.
# You should not need to modify these directly.
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
# LLM response parsing (internal helpers)
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


def _sanitize_control_chars(content: str) -> str:
    """Escape literal control characters inside JSON string values.

    LLaMA 3.1-8B frequently outputs bare newlines / tabs inside a
    "final_response" string, which are illegal unescaped in JSON (RFC 7159).
    This walks the raw text and replaces them only while inside a string.
    """
    result: list[str] = []
    in_string = False
    i = 0
    while i < len(content):
        c = content[i]
        if c == "\\" and i + 1 < len(content):
            result.append(c)
            result.append(content[i + 1])
            i += 2
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
        elif in_string and ord(c) < 0x20:
            if c == "\n":
                result.append("\\n")
            elif c == "\r":
                result.append("\\r")
            elif c == "\t":
                result.append("\\t")
            else:
                result.append(f"\\u{ord(c):04x}")
        else:
            result.append(c)
        i += 1
    return "".join(result)


def _parse_llm_json(content: str) -> dict[str, Any]:
    content = _sanitize_control_chars(content)
    content = _strip_markdown_code_fence(content)
    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise RuntimeError("LLM JSON response must be an object")
        return parsed
    except json.JSONDecodeError as exc:
        # JSONL (one tool_call per line) — handled below for the "Extra data" case.
        if "Extra data" in str(exc):
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            try:
                tool_calls: list[dict[str, Any]] = []
                for line in lines:
                    parsed_line = json.loads(line)
                    tc = parsed_line.get("tool_call") if isinstance(parsed_line, dict) else None
                    if isinstance(tc, dict):
                        tool_calls.append(tc)
                if tool_calls:
                    return {"tool_calls": tool_calls}
            except Exception:
                pass

    # Lenient recovery for weaker local models: extract the first {...} object and try
    # strict JSON, then Python-literal (handles single-quoted 'action'/'name' keys) +
    # trailing prose after the object.
    import ast as _ast
    a, b = content.find("{"), content.rfind("}")
    if a != -1 and b > a:
        frag = content[a:b + 1]
        for _loader in (json.loads, _ast.literal_eval):
            try:
                p = _loader(frag)
                if isinstance(p, dict):
                    return p
            except Exception:
                pass
    raise RuntimeError("Could not parse LLM JSON response")


def _normalize_llm_decision(parsed: dict[str, Any]) -> dict[str, Any]:
    action = parsed.get("action")

    if action == "final":
        return {"action": "final", "final_response": parsed["final_response"]}

    if action == "tool":
        tool_calls = parsed.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            raise RuntimeError("LLM tool decision must include a non-empty 'tool_calls' array")
        return {
            "action": "tool",
            "tool_calls": [{"name": t["name"], "arguments": t["arguments"]} for t in tool_calls],
        }

    if "final_response" in parsed:
        return {"action": "final", "final_response": parsed["final_response"]}

    tool_call = parsed.get("tool_call")
    if isinstance(tool_call, dict):
        return {
            "action": "tool",
            "tool_calls": [{"name": tool_call["name"], "arguments": tool_call["arguments"]}],
        }

    tool_calls = parsed.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        return {
            "action": "tool",
            "tool_calls": [{"name": t["name"], "arguments": t["arguments"]} for t in tool_calls],
        }

    raise RuntimeError("LLM response must include either 'final_response' or 'tool_call'")


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

    Returns one of:
      {"action": "final", "final_response": "<text>"}
      {"action": "tool",  "tool_calls": [{"name": "<tool>", "arguments": {...}}]}
    """
    formatted_prompt = system_prompt.format(tool_catalog=tool_catalog)
    llm_messages = [{"role": "system", "content": formatted_prompt}] + messages

    result = llm.invoke(llm_messages)
    content = result.content
    if not isinstance(content, str):
        raise RuntimeError("LLM response content must be a string")
    if not content.strip():
        raise RuntimeError(
            "LLM returned an empty response — the model may be unavailable or rate-limited"
        )

    try:
        return _normalize_llm_decision(_parse_llm_json(content))
    except Exception:
        print("\n[llm] Raw LLM response before crash:")
        print(content)
        raise


# ---------------------------------------------------------------------------
# Tool output persistence helper used by tool nodes
# ---------------------------------------------------------------------------

def write_tool_result(tool_output: str, path: Path) -> None:
    """Write a tool output to a file, pretty-printing JSON if possible."""
    stripped = tool_output.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        text = tool_output if tool_output.endswith("\n") else tool_output + "\n"
    else:
        text = json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
