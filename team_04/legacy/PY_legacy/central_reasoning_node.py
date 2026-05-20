from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


CENTRAL_REASONING_PROMPT = """
You are a design workflow AI.

Current design state:
{current_state}

Layout schema:
{layout_schema}

Available tools:
{tool_catalog}

Tool use rules:
- When the user asks to generate the site boundary, call the `site_boundary_generation` tool.
- Use the exact argument names from the tool input schema.
- Do not invent new argument names or return placeholder null values.
- If a required argument is missing, ask for clarification instead of calling the tool.

Return ONLY valid JSON.

Example:

{{
    "action": "tool",
    "tool_calls": [
        {{
            "name": "site_boundary",
            "arguments": {{
                "area": 50000,
                "sides": 4
            }}
        }}
    ]
}}
"""


_LAYOUT_SCHEMA_CACHE: dict[str, Any] | None = None


def _load_layout_schema() -> dict[str, Any]:
    global _LAYOUT_SCHEMA_CACHE
    if _LAYOUT_SCHEMA_CACHE is None:
        schema_path = Path(__file__).with_name("layout_schema.json")
        try:
            _LAYOUT_SCHEMA_CACHE = json.loads(schema_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _LAYOUT_SCHEMA_CACHE = {}
        except json.JSONDecodeError:
            _LAYOUT_SCHEMA_CACHE = {}
    cached_schema = _LAYOUT_SCHEMA_CACHE
    if cached_schema is None:
        return {}
    return deepcopy(cached_schema)


def _resolve_schema_tool_calls(
    layout_schema: dict[str, Any], parsed: dict[str, Any]
) -> list[dict[str, Any]]:
    if isinstance(layout_schema, dict):
        workflow = layout_schema.get("workflow")
        if isinstance(workflow, dict):
            schema_tool_calls = workflow.get("tool_calls")
            if isinstance(schema_tool_calls, list):
                return [call for call in schema_tool_calls if isinstance(call, dict)]

            active_tool = workflow.get("active_tool")
            if isinstance(active_tool, str) and active_tool.strip():
                tool_arguments = workflow.get("tool_arguments", {})
                if not isinstance(tool_arguments, dict):
                    tool_arguments = {}
                return [{"name": active_tool, "arguments": tool_arguments}]

    parsed_tool_calls = parsed.get("tool_calls")
    if isinstance(parsed_tool_calls, list):
        resolved_tool_calls = [call for call in parsed_tool_calls if isinstance(call, dict)]
        if resolved_tool_calls:
            return resolved_tool_calls

    legacy_tool_name = parsed.get("tool") or parsed.get("tool_name") or parsed.get("name")
    if isinstance(legacy_tool_name, str) and legacy_tool_name.strip():
        legacy_arguments = parsed.get("arguments", {})
        if not isinstance(legacy_arguments, dict):
            legacy_arguments = {}
        return [{"name": legacy_tool_name.strip(), "arguments": legacy_arguments}]

    return []


def _extract_generated_options(parsed: dict[str, Any], tool_calls: list[dict[str, Any]]) -> list[str]:
    suggestions = parsed.get("suggestions")
    if isinstance(suggestions, list):
        option_texts = [option.strip() for option in suggestions if isinstance(option, str) and option.strip()]
        if option_texts:
            return option_texts

    if tool_calls:
        option_texts: list[str] = []
        for tool_call in tool_calls:
            name = tool_call.get("name")
            if isinstance(name, str) and name.strip():
                option_texts.append(name.strip())
        if option_texts:
            return option_texts

    return []


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
        raise RuntimeError(f"Invalid JSON: {exc}") from exc


def create_central_reasoning_node(
    llm: Any, dbg: Callable[[str], None], tool_names: list[str] | str | None = None
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """
    Create the central reasoning node that decides what design action to take next.
    This is the hub of the entire workflow.
    """

    def central_reasoning_node(state: dict[str, Any], /) -> dict[str, Any]:
        dbg("[workflow][central_reason] Enter node")

        tool_catalog_text = "none"
        if isinstance(tool_names, str) and tool_names.strip():
            tool_catalog_text = tool_names.strip()
        elif tool_names:
            tool_catalog_text = "\n".join(f"- {name}" for name in tool_names)

        current_schema = state.get("layout_schema")
        if not isinstance(current_schema, dict) or not current_schema:
            current_schema = _load_layout_schema()

        system_prompt = CENTRAL_REASONING_PROMPT.format(
            current_state=json.dumps(state.get("design_state", {}), indent=2),
            tool_catalog=tool_catalog_text,
            layout_schema=json.dumps(current_schema, indent=2),
        )

        llm_messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state.get("user_prompt", "")},
        ]

        if state.get("feedback_history"):
            for feedback in state.get("feedback_history", []):
                llm_messages.append({"role": "user", "content": feedback})

        dbg("[workflow][central_reason] Calling LLM")
        start_time = time.perf_counter()
        result = llm.invoke(llm_messages)
        elapsed = time.perf_counter() - start_time
        dbg(f"[workflow][central_reason] LLM response received in {elapsed:.2f}s")
        content = _normalize_content_text(result.content)

        if not content.strip():
            dbg("[workflow][central_reason] Empty LLM output")
            state["pending_action"] = "ask_user"
            state["pending_tool_calls"] = []
            return state

        try:
            parsed = _parse_llm_json(content)
        except Exception as exc:
            dbg(f"[workflow][central_reason] Parse error: {exc}")
            state["pending_action"] = "ask_user"
            state["pending_tool_calls"] = []
            return state

        action = parsed.get("action", "ask_user")
        reasoning = parsed.get("reasoning", "")

        layout_schema = parsed.get("layout_schema")
        if not isinstance(layout_schema, dict):
            layout_schema = current_schema

        tool_calls = _resolve_schema_tool_calls(layout_schema, parsed)
        generated_options = _extract_generated_options(parsed, tool_calls)

        if len(generated_options) > 1 and action != "final":
            dbg(
                f"[workflow][central_reason] Multiple options generated ({len(generated_options)}), requesting user feedback"
            )
            state["pending_action"] = "ask_user"
            state["pending_tool_calls"] = tool_calls
            state["last_reasoning"] = reasoning
            state["next_step"] = parsed.get("next_step", "")
            state["layout_schema"] = layout_schema
            state["design_state"]["generated_options"] = generated_options
            return state

        if action == "ask_user" and len(generated_options) <= 1:
            dbg("[workflow][central_reason] Single option generated, returning direct result")
            state["pending_action"] = "final"
            state["pending_tool_calls"] = []
            state["last_reasoning"] = reasoning
            state["next_step"] = parsed.get("next_step", "")
            state["layout_schema"] = layout_schema
            single_option = generated_options[0] if generated_options else reasoning
            state["final_response"] = parsed.get("final_response", single_option or "Design complete.")
            return state

        dbg(f"[workflow][central_reason] Decision: action={action}, reasoning={reasoning}")

        state["pending_action"] = action
        state["pending_tool_calls"] = tool_calls
        state["last_reasoning"] = reasoning
        state["next_step"] = parsed.get("next_step", "")
        state["layout_schema"] = layout_schema

        if action == "final":
            state["final_response"] = parsed.get("final_response", "Design complete.")

        return state

    return central_reasoning_node
