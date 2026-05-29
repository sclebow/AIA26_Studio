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
) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=llm_model,
        timeout=timeout_seconds,
        temperature=0,
        max_tokens=8192,
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
        "required": [],
        "additionalProperties": False,
    }


def get_llm_response_format(tools: list[dict[str, Any]]) -> dict[str, Any]:
    # Return empty — no response_format overhead.
    # The system prompt already instructs the model to output strict JSON,
    # and _parse_llm_json handles parsing the free-text response.
    return {}


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

def _call_api_direct(llm: Any, messages: list[dict]) -> Any:
    """Fallback: direct httpx call to the OpenAI-compatible endpoint.

    Some providers (Cloudflare Workers AI) return `content` as a parsed dict
    rather than a JSON string, which langchain-openai rejects with a
    ValidationError inside llm.invoke().  This bypasses LangChain entirely
    and returns the raw content value (str or dict).
    """
    import httpx

    api_key_obj = getattr(llm, "openai_api_key", None)
    api_key = (
        api_key_obj.get_secret_value()
        if hasattr(api_key_obj, "get_secret_value")
        else str(api_key_obj or "")
    )
    base_url = str(getattr(llm, "openai_api_base", None) or "").rstrip("/")
    model    = str(getattr(llm, "model_name", None) or getattr(llm, "model", ""))
    # ChatOpenAI stores timeout as `request_timeout` internally (alias "timeout")
    timeout  = float(
        getattr(llm, "request_timeout", None)
        or getattr(llm, "timeout", None)
        or 60
    )
    max_tok  = int(getattr(llm, "max_tokens", None) or 8192)

    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model":       model,
            "messages":    messages,
            "temperature": 0,
            "max_tokens":  max_tok,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_llm(
    llm: Any,
    system_prompt: str,
    messages: list[dict[str, str]],
    tool_catalog: str | None = None,
) -> dict[str, Any]:
    """Invoke the LLM and return a parsed decision dict.

    Returns one of:
      {"action": "final", "final_response": "<text>"}
      {"action": "tool",  "tool_calls": [{"name": "<tool>", "arguments": {...}}]}
    """
    formatted_prompt = (
        system_prompt.format(tool_catalog=tool_catalog)
        if tool_catalog is not None
        else system_prompt
    )
    llm_messages = [{"role": "system", "content": formatted_prompt}] + messages

    # ── Primary: LangChain invoke ─────────────────────────────────────────────
    content: Any
    try:
        result = llm.invoke(llm_messages)
        content = result.content
    except Exception as exc:
        # Cloudflare Workers AI returns `content` as a parsed dict, which
        # langchain-openai rejects with a ValidationError. Fall back to a
        # direct httpx call that handles both str and dict content.
        if type(exc).__name__ not in ("ValidationError", "PydanticValidationError", "ValueError"):
            raise
        content = _call_api_direct(llm, llm_messages)

    if isinstance(content, dict):
        return _normalize_llm_decision(content)
    if not isinstance(content, str):
        raise RuntimeError(f"LLM response content must be a string or dict, got {type(content)}")

    # If the model returned empty content (e.g. empty markdown fence ``` ```)
    # retry once via the direct httpx path which uses the full timeout.
    # Check AFTER fence-stripping so ``` ```json\n\n``` ``` is also caught.
    if not _strip_markdown_code_fence(content).strip():
        print("[llm] Empty content from LLM, retrying via direct httpx call")
        content = _call_api_direct(llm, llm_messages)
        if isinstance(content, dict):
            return _normalize_llm_decision(content)
        if not isinstance(content, str):
            raise RuntimeError(f"Retry returned unexpected type: {type(content)}")

    try:
        return _normalize_llm_decision(_parse_llm_json(content))
    except Exception:
        # Model returned non-JSON plain text (e.g. a prose report).
        # If the stripped content is non-empty, wrap it as a final_response
        # so the workflow can continue rather than crashing.
        stripped = _strip_markdown_code_fence(content)
        if stripped.strip():
            print("[llm] Non-JSON response — treating as plain-text final_response")
            return {"action": "final", "final_response": stripped}
        print("\n[llm] Raw LLM response before crash:")
        print(repr(content))
        raise


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
