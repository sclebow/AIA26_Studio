from __future__ import annotations

from copy import deepcopy
from typing import Any
from langchain_openai import ChatOpenAI


# Base schema for LLM decisions
DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reasoning": {
            "type": "string",
            "description": "Explanation of the decision",
        },
        "action": {
            "type": "string",
            "enum": ["suggest", "evaluate", "optimize", "explain", "visualize", "tool", "ask_user", "final"],
        },
        "tool_calls": {
            "type": "array",
            "description": "Tool calls to execute",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "arguments": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": True,
                    },
                },
                "required": ["name", "arguments"],
                "additionalProperties": False,
            },
        },
        "next_step": {
            "type": "string",
            "description": "Description of what happens next",
        },
        "final_response": {
            "type": "string",
            "description": "Final response if action is 'final'",
        },
    },
    "required": ["action", "tool_calls"],
    "additionalProperties": False,
}


def get_llm_response_format(tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """
    Generates a JSON schema for the LLM's response format.
    Tailored to available tools if provided.
    """

    schema = deepcopy(DECISION_SCHEMA)

    if tools:
        tool_names = [str(tool.get("name")) for tool in tools if tool.get("name")]
        if tool_names:
            tool_call_schema = schema["properties"]["tool_calls"]["items"]
            tool_call_schema["properties"]["name"]["enum"] = tool_names

    return {
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "design_decision",
                "strict": True,
                "schema": schema,
            },
        }
    }


def create_chat_llm(
    api_key: str,
    base_url: str,
    llm_model: str,
    timeout_seconds: float,
    model_kwargs: dict[str, Any] | None = None,
) -> ChatOpenAI:
    """
    Create a ChatOpenAI LLM instance with design workflow configuration.
    """

    effective_model_kwargs = model_kwargs or {}
    if llm_model.strip().lower() == "local":
        effective_model_kwargs = {}

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=llm_model,
        timeout=timeout_seconds,
        temperature=0,
        model_kwargs=effective_model_kwargs,
    )
