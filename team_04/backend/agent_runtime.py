"""Lazily construct the Team 04 agent graph for the chat endpoint.

The chat router needs a compiled LangGraph app to stream events from, but
``agent.graph.build_agent_graph`` requires ``(decision_engine, tool_client,
catalog)`` — the router previously called it with no arguments, so the agent
never actually ran and every chat turn errored out before the first node.

This module mirrors ``agent/main.py``'s wiring (settings → LLM engine + tool
client + catalog → compiled app) and caches a single app for the server
process so the LLM/MCP clients are built once, not per request.
"""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_app: Any = None


def get_agent_app() -> Any:
    """Return the process-wide compiled agent graph, building it on first use.

    Thread-safe double-checked lazy init. Raises if the LLM environment is not
    configured — the chat router surfaces that as an SSE ``error`` event, same
    as any other agent failure.
    """
    global _app
    if _app is not None:
        return _app
    with _lock:
        if _app is None:
            _app = _build_app()
    return _app


def _build_app() -> Any:
    from langchain_openai import ChatOpenAI

    from agent.config import load_settings
    from agent.decision_engine import OpenAIDecisionEngine, RuleBasedPlanner
    from agent.graph import build_agent_graph
    from agent.mcp_client import (
        CompositeToolClient,
        HttpMcpClient,
        build_default_local_tool_client,
    )
    from agent.tool_catalog import ToolCatalog

    settings = load_settings()

    # Local geometry tools always available; add MCP tools when reachable.
    local_client = build_default_local_tool_client()
    try:
        mcp_client = HttpMcpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
        mcp_client.initialize()
        client: Any = CompositeToolClient([local_client, mcp_client])
    except Exception:
        client = local_client

    catalog = ToolCatalog.from_discovered_tools(client.list_tools())
    llm = ChatOpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        model=settings.llm_model,
        timeout=settings.request_timeout_seconds,
        temperature=0,
    )
    engine = OpenAIDecisionEngine(
        llm=llm,
        decision_provider=settings.decision_llm_provider,
        decision_model=settings.decision_llm_model,
        report_provider=settings.report_llm_provider,
        report_model=settings.report_llm_model,
    )
    return build_agent_graph(engine, client, catalog, planner=RuleBasedPlanner())
