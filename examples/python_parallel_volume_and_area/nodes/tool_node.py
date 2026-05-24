from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Callable
from langchain_openai import ChatOpenAI

from mcp_client import McpClient


# The LLM_DECISION_SCHEMA defines the expected JSON schema for the LLM's decision output.
# I've had to write this to be compatible with all of the LLM providers we support.
# You should not need to modify this schema directly; 
# instead, use `get_llm_response_format` to generate a schema tailored to the tools you have.
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
    '''
    Builds a JSON schema for the arguments of the given tools, merging their input schemas.
    This is used to generate the LLM response format for tool calls.
    '''

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
    '''
    Generates a JSON schema for the LLM's response format, tailored to the given tools.
    This schema ensures that the LLM's output conforms to the expected structure for tool calls.
    '''

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


def create_chat_llm(
    api_key: str,
    base_url: str,
    llm_model: str,
    timeout_seconds: float,
    model_kwargs: dict[str, Any] | None = None,
) -> ChatOpenAI:
    '''
    Both the classifier and the domain sub-agents use the same model settings.
    This helper keeps that setup in one place so the code stays easy to read.
    '''

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


def create_tool_node(
    mcp_client: McpClient,
    allowed_tools: list[dict[str, Any]],
    dbg: Callable[[str], None],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    '''
    Creates a tool node function that can be used in a graph execution context.
    The tool node will process pending tool calls in the state, call the appropriate tools
    via the MCP client, and update the state with the results.
    '''

    allowed_tool_names = {str(tool.get("name")) for tool in allowed_tools if tool.get("name")}

    def tool_node(state: dict[str, Any]) -> dict[str, Any]:
        dbg("[graph][tool] Enter node")
        if not state["pending_tool_calls"]:
            raise RuntimeError("Tool node called without pending tool call")

        for pending_tool in state["pending_tool_calls"]:
            state["iteration"] += 1
            if state["iteration"] > state["max_iterations"]:
                raise RuntimeError("Max iterations exceeded")

            tool_name = pending_tool["tool_name"]
            if tool_name not in allowed_tool_names:
                raise RuntimeError(f"Tool '{tool_name}' is not allowed in this domain")

            raw_tool_arguments = pending_tool["arguments"]
            if not isinstance(raw_tool_arguments, dict):
                raise RuntimeError("Tool arguments must be an object")

            tool_arguments = {
                key: value for key, value in raw_tool_arguments.items() if value is not None
            }

            dbg(
                f"[graph][tool] Calling tool | iteration={state['iteration']} | "
                f"name={tool_name} | args={tool_arguments}"
            )

            tool_output = mcp_client.call_tool(tool_name, tool_arguments)
            dbg(f"[graph][tool] Tool output: {tool_output}")

            state["messages"].append(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "action": "tool",
                            "final_response": "",
                            "tool_calls": [
                                {
                                    "name": tool_name,
                                    "arguments": tool_arguments,
                                }
                            ],
                        }
                    ),
                }
            )
            state["messages"].append(
                {
                    "role": "user",
                    "content": f"Tool result: {tool_output}",
                }
            )

        state["pending_tool_calls"] = None
        return state

    return tool_node
