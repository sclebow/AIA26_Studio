"""Builds and caches the REAL agent — the same construction agent/main.py uses.

Nothing here reimplements agent behaviour. It wires the existing pieces:

    settings  -> agent.config.load_settings()
    LLM       -> langchain_openai.ChatOpenAI(...)
    engine    -> agent.decision_engine.OpenAIDecisionEngine(...)
    tools     -> agent.mcp_client local client (+ optional HTTP MCP)
    catalog   -> agent.tool_catalog.ToolCatalog.from_discovered_tools(...)
    graph     -> agent.graph.build_agent_graph(engine, client, catalog, planner)

If the environment isn't configured (no API key / no MCP), building the LLM
engine raises — we surface that error to the caller instead of faking a graph.
The compiled LangGraph is cached process-wide; it is stateless across runs
(state is passed in per-invoke), so one instance serves every session.
"""
from __future__ import annotations

import threading
from typing import Any

# Importing this package puts team_04/ on sys.path so `agent.*` resolves.
from . import _TEAM_ROOT  # noqa: F401  (side-effect import)

_lock = threading.Lock()
_cache: dict[str, Any] = {}


def _build() -> dict[str, Any]:
    """Construct engine + client + catalog + compiled graph once."""
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

    local_client = build_default_local_tool_client()
    clients = [local_client]
    # The HTTP MCP server is optional — if it isn't reachable, the local tool
    # client still covers the core boundary/placement tools, so we don't hard-fail.
    try:
        mcp_client = HttpMcpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
        mcp_client.initialize()
        clients.append(mcp_client)
    except Exception as exc:  # noqa: BLE001
        print(f"[connection] HTTP MCP unavailable, using local tools only: {exc}")

    client = CompositeToolClient(clients)
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
    planner = RuleBasedPlanner()
    graph = build_agent_graph(engine, client, catalog, planner=planner)

    return {
        "settings": settings,
        "client": client,
        "catalog": catalog,
        "engine": engine,
        "planner": planner,
        "graph": graph,
    }


def get_runtime() -> dict[str, Any]:
    """Return the cached runtime, building it on first use.

    Raises whatever load_settings()/ChatOpenAI raise if the environment is not
    configured — the caller turns that into an SSE 'error' event so the user sees
    a real reason rather than a silent stub.
    """
    with _lock:
        if not _cache:
            _cache.update(_build())
        return _cache


def get_graph() -> Any:
    return get_runtime()["graph"]


def get_tool_client() -> Any:
    return get_runtime()["client"]


def get_catalog() -> Any:
    return get_runtime()["catalog"]


def is_ready() -> bool:
    """True if the runtime can be built (env configured). Never raises."""
    try:
        get_runtime()
        return True
    except Exception:  # noqa: BLE001
        return False
