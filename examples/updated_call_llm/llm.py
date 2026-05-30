from __future__ import annotations
from copy import deepcopy
import json
import os
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

    raise RuntimeError(
        "LLM response must be a single JSON object matching the decision schema"
    )


def _normalize_llm_decision(parsed: dict[str, Any]) -> dict[str, Any]:
    action = parsed.get("action")

    if action == "final":
        return {"action": "final", "agent_calls": [], "response": parsed.get("response", "")}
    elif action == "agent":
        return {"action": "agent", "agent_calls": parsed.get("agent_calls", []), "response": ""}
    elif action == "further_thought":
        return {"action": "further_thought", "agent_calls": [], "response": parsed.get("response", "")}

    raise RuntimeError("LLM response must include either 'final', 'agent', or 'further_thought'")


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing or empty required environment variable: {name}")
    return value


def _resolve_llm_connection(
    provider: str,
    model: str | None,
) -> tuple[str, str, str]:
    normalized_provider = provider.strip().lower()

    if normalized_provider == "local":
        api_key = "No API Key Required"
        base_url = _required_env("LOCAL_LLM_ENDPOINT")
        resolved_model = model or "local"

    elif normalized_provider == "cloudflare":
        api_key = _required_env("CF_API_TOKEN")
        account_id = _required_env("CF_ACCOUNT_ID")
        base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
        resolved_model = model or _required_env("CF_MODEL")

    elif normalized_provider == "openai":
        api_key = _required_env("OPENAI_API_KEY")
        base_url = "https://api.openai.com/v1"
        resolved_model = model or _required_env("OPENAI_MODEL")

    elif normalized_provider == "google":
        api_key = _required_env("GOOGLE_API_KEY")
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        resolved_model = model or _required_env("GOOGLE_MODEL")

    elif normalized_provider == "anthropic":
        api_key = _required_env("ANTHROPIC_API_KEY")
        base_url = "https://api.anthropic.com/v1/"
        resolved_model = model or _required_env("ANTHROPIC_MODEL")

    else:
        raise ValueError(f"Unsupported provider override: {provider}")

    return api_key, base_url, resolved_model


def _resolve_timeout_seconds(llm: Any) -> float:
    timeout = getattr(llm, "timeout", None)
    if isinstance(timeout, (int, float)) and timeout > 0:
        return float(timeout)
    return 30.0


# ---------------------------------------------------------------------------
# Public convenience function used by reason nodes
# ---------------------------------------------------------------------------

def call_llm(
    llm: Any,
    system_prompt: str,
    messages: list[dict[str, str]],
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Invoke the LLM and return a parsed decision dict.

    provider and model are optional per-call overrides for .env defaults.
    """
    
    llm_messages = [{"role": "system", "content": system_prompt}] + messages

    active_llm = llm
    if provider is not None or model is not None:
        resolved_provider = provider or os.environ.get("LLM_PROVIDER", "")
        if not resolved_provider:
            raise RuntimeError("LLM_PROVIDER is required when using call_llm overrides")

        api_key, base_url, resolved_model = _resolve_llm_connection(resolved_provider, model)
        model_kwargs = getattr(llm, "model_kwargs", {})
        if not isinstance(model_kwargs, dict):
            model_kwargs = {}

        active_llm = create_chat_llm(
            api_key=api_key,
            base_url=base_url,
            llm_model=resolved_model,
            timeout_seconds=_resolve_timeout_seconds(llm),
            model_kwargs=model_kwargs,
        )

    result = active_llm.invoke(llm_messages)
    content = result.content
    if not isinstance(content, str):
        raise RuntimeError("LLM response content must be a string")

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
