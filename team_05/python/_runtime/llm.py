from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Union
from langchain_anthropic import ChatAnthropic
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
) -> Union[ChatAnthropic, ChatOpenAI]:
    model_name = llm_model.lower()

    if "claude" in llm_model.lower():
        return ChatAnthropic(
            api_key=api_key,
            base_url=base_url,
            model=llm_model,
            timeout=timeout_seconds,
            temperature=0,
            model_kwargs=model_kwargs or {},
            max_tokens=2000
        )
    elif "gpt" in model_name or "gemini" in model_name:
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=llm_model,
            timeout=timeout_seconds,
            temperature=0,
            model_kwargs=model_kwargs or {},
            max_tokens=2000
        )
    
    elif "ChatAnthropic" in llm_model:
        return ChatAnthropic(
            api_key=api_key,
            base_url=base_url,
            model=llm_model,
            timeout=timeout_seconds,
            temperature=0,
            model_kwargs=model_kwargs or {},
            max_tokens=2000
        )
    
    elif "local" in llm_model:
        return ChatOpenAI(
            base_url=base_url or "http://localhost:1234/v1",
            api_key="lm-studio",  # dummy key (LM Studio ignore eder)
            model=llm_model,
            temperature=0,
            timeout=timeout_seconds,
            max_tokens=2000,
            model_kwargs=model_kwargs or {},
        )
    else:
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=llm_model,
            timeout=timeout_seconds,
            temperature=0,
            model_kwargs=model_kwargs or {},
            max_tokens=2000)
    

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


def _extract_json_object(content: str) -> str:
    """Find and return the first complete {...} block in content."""
    start = content.find("{")
    if start == -1:
        return content
    depth = 0
    for i, ch in enumerate(content[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return content[start : i + 1]
    return content[start:]


def _parse_llm_json(content: str) -> dict[str, Any]:
    content = _strip_markdown_code_fence(content)
    content = _extract_json_object(content)
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

_JSON_INSTRUCTION = """
IMPORTANT: You must respond with ONLY a valid JSON object — no prose, no markdown, no XML.
Use exactly this schema:

To call a tool:
{"action": "tool", "final_response": "", "tool_calls": [{"name": "<tool_name>", "arguments": {<key>: <value>}}]}

To give a final answer:
{"action": "final", "final_response": "<your answer here>", "tool_calls": []}

Do not include any text outside the JSON object.
"""


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
    formatted_prompt = system_prompt.format(tool_catalog=tool_catalog) + _JSON_INSTRUCTION
    llm_messages = [{"role": "system", "content": formatted_prompt}] + messages

    try:
      result = llm.invoke(llm_messages)
    except Exception as e:
       print(f"[llm] Error: {e}")
       print(f"[llm] Last response object: {getattr(e, 'completion', None)}")
       raise
    content = result.content
    if isinstance(content, list):
        # ChatAnthropic returns a list of content blocks; extract text parts
        content = " ".join(
            block["text"] for block in content
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
        )
    if not isinstance(content, str):
        raise RuntimeError(f"LLM response content must be a string, got: {type(content)}")

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
