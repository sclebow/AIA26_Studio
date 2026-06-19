from __future__ import annotations
import contextvars
from copy import deepcopy
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional
from langchain_openai import ChatOpenAI


# ---------------------------------------------------------------------------
# Token streaming sink (SSE)
#
# A ContextVar carrying an optional callback that receives final-answer token
# chunks as they are generated. run_agent_stream() sets this in the worker thread
# before driving the graph; the respond node reads it and streams its LLM output
# token-by-token to the SSE layer. Default None → all nodes behave exactly as the
# non-streaming path (call_llm_simple), so this is invisible to /api/message.
# ---------------------------------------------------------------------------

_TOKEN_SINK: "contextvars.ContextVar[Optional[Callable[[str], None]]]" = (
    contextvars.ContextVar("sensi_token_sink", default=None)
)

# A no-arg callback a terminal text node calls at the START of generation (before
# any tokens) to mark a fresh message. Lets the SSE layer reset the client buffer
# cleanly when respond runs twice (evaluator REVISE loop) — no node-order guessing.
_MSG_START_SINK: "contextvars.ContextVar[Optional[Callable[[], None]]]" = (
    contextvars.ContextVar("sensi_msg_start_sink", default=None)
)


def set_token_sink(fn: Optional[Callable[[str], None]]):
    """Install a token sink for the current context; returns a reset token."""
    return _TOKEN_SINK.set(fn)


def reset_token_sink(token) -> None:
    _TOKEN_SINK.reset(token)


def get_token_sink() -> Optional[Callable[[str], None]]:
    return _TOKEN_SINK.get()


def set_message_start_sink(fn: Optional[Callable[[], None]]):
    return _MSG_START_SINK.set(fn)


def reset_message_start_sink(token) -> None:
    _MSG_START_SINK.reset(token)


def get_message_start_sink() -> Optional[Callable[[], None]]:
    return _MSG_START_SINK.get()


# ---------------------------------------------------------------------------
# Token-usage accounting (benchmarking — see bench_nodes.py)
#
# Every llm.invoke() result from an OpenAI-compatible endpoint (incl. Google's)
# carries usage_metadata{input_tokens, output_tokens}. We accumulate it in a
# module-level counter so the graph's per-node timer (graph.py, gated on
# BENCH_NODES) can snapshot the delta around each node and attribute tokens/cost.
# Cheap and always-on; ignored unless someone reads the snapshot.
# ---------------------------------------------------------------------------

_USAGE = {"calls": 0, "input": 0, "output": 0}


def _record_usage(result: Any) -> None:
    um = getattr(result, "usage_metadata", None)
    if isinstance(um, dict):
        _USAGE["calls"] += 1
        _USAGE["input"] += int(um.get("input_tokens", 0) or 0)
        _USAGE["output"] += int(um.get("output_tokens", 0) or 0)


def usage_snapshot() -> dict:
    """A copy of the running token counter (calls/input/output)."""
    return dict(_USAGE)


def usage_reset() -> None:
    _USAGE.update(calls=0, input=0, output=0)


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
    _record_usage(result)
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
# Per-call provider/model override (benchmarking)
#
# Mirrors the faculty example (examples/updated_call_llm/llm.py): an optional
# provider+model override lets a single call hit a different model/provider than
# the one configured in .env — handy for ad-hoc A/B comparisons. The per-node
# tiers in bootstrap.py (llm_fast / llm_smart) cover the common case; this is the
# escape hatch for one-off experiments.
# ---------------------------------------------------------------------------

def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing or empty required environment variable: {name}")
    return value


def _resolve_llm_connection(provider: str, model: str | None) -> tuple[str, str, str]:
    """Resolve (api_key, base_url, model) for a provider override. Same provider
    set as _runtime/config.py."""
    normalized = provider.strip().lower()

    if normalized == "local":
        return "No API Key Required", _required_env("LOCAL_LLM_ENDPOINT"), (model or "local")
    if normalized == "cloudflare":
        account_id = _required_env("CF_ACCOUNT_ID")
        return (
            _required_env("CF_API_TOKEN"),
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
            model or _required_env("CF_MODEL"),
        )
    if normalized == "openai":
        return _required_env("OPENAI_API_KEY"), "https://api.openai.com/v1", (model or _required_env("OPENAI_MODEL"))
    if normalized == "google":
        return (
            _required_env("GOOGLE_API_KEY"),
            "https://generativelanguage.googleapis.com/v1beta/openai",
            model or _required_env("GOOGLE_MODEL"),
        )
    if normalized == "anthropic":
        return _required_env("ANTHROPIC_API_KEY"), "https://api.anthropic.com/v1/", (model or _required_env("ANTHROPIC_MODEL"))

    raise ValueError(f"Unsupported provider override: {provider}")


def _resolve_timeout_seconds(llm: Any) -> float:
    timeout = getattr(llm, "timeout", None)
    if isinstance(timeout, (int, float)) and timeout > 0:
        return float(timeout)
    return 30.0


def _apply_overrides(llm: Any, provider: str | None, model: str | None) -> Any:
    """Return a one-off LLM honoring provider/model overrides, or the original llm
    when no override is requested."""
    if provider is None and model is None:
        return llm
    resolved_provider = provider or os.environ.get("LLM_PROVIDER", "")
    if not resolved_provider:
        raise RuntimeError("LLM_PROVIDER is required when overriding the model")
    api_key, base_url, resolved_model = _resolve_llm_connection(resolved_provider, model)
    return create_chat_llm(
        api_key=api_key,
        base_url=base_url,
        llm_model=resolved_model,
        timeout_seconds=_resolve_timeout_seconds(llm),
        model_kwargs=None,
    )


# ---------------------------------------------------------------------------
# Simple LLM call — no tool catalog, just system + user message → string
# Used by chitchat, respond, and other free-text reasoning nodes.
# ---------------------------------------------------------------------------

def _strip_think_tags(text: str) -> str:
    """
    Remove <think>...</think> reasoning blocks produced by Qwen3, DeepSeek-R1,
    and similar models.  Safe to call on any LLM output — if no think block
    exists the string is returned unchanged.
    """
    import re
    try:
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    except Exception:
        return text


def call_llm_simple(
    llm: Any,
    system_prompt: str,
    user_message: str,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    """Invoke the LLM with a plain system + user message and return the response string.

    Pass a plain LLM instance (no response_format / JSON schema) so the model
    can respond freely without token budget wasted on JSON wrapper.
    Use ctx.llm_simple, not ctx.llm, when calling this function.

    provider and model are optional per-call overrides (benchmarking). When
    omitted, the passed-in llm is used as-is — so the per-node tiers wired in
    bootstrap.py (ctx.llm_fast / ctx.llm_smart) are the normal path.

    Think tags (<think>...</think>) produced by reasoning models (Qwen3,
    DeepSeek-R1) are stripped automatically before the string is returned.
    """
    llm = _apply_overrides(llm, provider, model)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    result = llm.invoke(messages)
    _record_usage(result)
    content = result.content
    if not isinstance(content, str):
        raise RuntimeError("LLM response content must be a string")

    stripped = _strip_think_tags(content)
    # Reasoning models (qwen3, DeepSeek-R1) sometimes spend the whole turn inside a
    # <think> block and emit no final answer, leaving an empty string after stripping.
    # Retry once — the second pass usually produces a real answer.
    if not stripped.strip():
        print("[llm] Empty answer after think-strip — retrying once.")
        result = llm.invoke(messages)
        _record_usage(result)
        content = result.content if isinstance(result.content, str) else ""
        stripped = _strip_think_tags(content)
    return stripped


def call_llm_simple_streaming(
    llm: Any,
    system_prompt: str,
    user_message: str,
    on_token: Callable[[str], None],
    provider: str | None = None,
    model: str | None = None,
) -> str:
    """Like call_llm_simple, but streams the response token-by-token to on_token
    as it is generated, and returns the full assembled string.

    Same contract as call_llm_simple (think-tag strip + usage accounting + returns
    a plain string). Used by the respond node when a token sink is active so the
    final user-facing answer flows to the SSE stream incrementally. Falls back to a
    non-streaming call if the stream yields nothing usable.

    NOTE: tokens are emitted as the model produces them, so for reasoning models
    that wrap output in <think>…</think> those tokens would stream visibly. The
    configured provider (Google Gemini) does not emit think tags, so this is safe
    here; if a reasoning model is ever configured, prefer call_llm_simple.
    """
    llm = _apply_overrides(llm, provider, model)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    full = ""
    aggregate = None
    try:
        for chunk in llm.stream(messages):
            aggregate = chunk if aggregate is None else aggregate + chunk
            piece = chunk.content if isinstance(chunk.content, str) else ""
            if piece:
                full += piece
                try:
                    on_token(piece)
                except Exception:
                    pass  # a failing sink must never break generation
    except Exception as exc:
        print(f"[llm] Streaming failed ({exc}) — falling back to non-streaming call.")
        return call_llm_simple(llm, system_prompt, user_message)

    # usage_metadata rides on the final aggregated chunk when the provider includes
    # it; record best-effort so benchmarking still attributes streamed tokens.
    if aggregate is not None:
        _record_usage(aggregate)

    stripped = _strip_think_tags(full)
    if not stripped.strip():
        print("[llm] Empty streamed answer — retrying once (non-streaming).")
        return call_llm_simple(llm, system_prompt, user_message)
    return stripped


def respond_text(llm: Any, system_prompt: str, user_message: str) -> str:
    """Generate a terminal, user-facing message.

    When a token sink is installed (run_agent_stream), signal a fresh message and
    stream the answer token-by-token; otherwise behave EXACTLY as call_llm_simple.
    Use this only for nodes whose output IS the user-facing answer (respond,
    detail_respond, chitchat) — never for internal nodes (score_interpreter,
    evaluator, what_next, …) so only the answer streams, not the scaffolding.
    """
    sink = get_token_sink()
    if sink is None:
        return call_llm_simple(llm, system_prompt, user_message)
    start = get_message_start_sink()
    if start is not None:
        try:
            start()
        except Exception:
            pass
    return call_llm_simple_streaming(llm, system_prompt, user_message, sink)


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
