"""Shared runtime modules — the SINGLE implementation used by both the
notebooks (validation layer) and the frontend (via connection/routes).

Architecture:

    frontend2 ──▶ connection/routes ──▶ connection/notebook_logic ──▶ agent.* / connection.*
    notebooks  ───────────────────────▶ connection/notebook_logic ──▶ agent.* / connection.*

These modules do NOT reimplement any algorithm. They are thin orchestration +
payload-shaping wrappers over the existing, notebook-tested logic in:

    agent.tools.*          — geometry generation, modification, view analysis, optimization
    agent.graph            — the LangGraph agent workflow
    agent.decision_engine  — planner + supervisor
    connection.decision_graph — the design DAG
    connection.agent_runtime  — the cached compiled agent graph

Every module loads the confirmed site (connection/data/confirmed_site.json) via
site_state when no explicit boundary is supplied, so geometry, optimization, the
decision graph, and the agent workflow all share one site of truth.
"""
from __future__ import annotations

# Importing the connection package puts team_04/ on sys.path so `agent.*` resolves
# regardless of the current working directory (notebook vs. server).
from .. import _TEAM_ROOT  # noqa: F401  (side-effect import)
