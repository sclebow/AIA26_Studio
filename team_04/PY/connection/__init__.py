"""Connection layer — the HTTP bridge between frontend2 and the real agent.

This package is NOT a reimplementation of the agent. It is a thin FastAPI server
that:

  * builds the *existing* agent (agent.graph / agent.tools / agent.decision_engine)
    exactly the way agent/main.py does, and
  * exposes it over the routes the notebooks and frontend2 expect:
      /sessions, /sessions/{id}/chat (SSE), /sessions/{id}/decisions,
      /sessions/{id}/explorer, /tools.

Run it (from team_04/PY):
    uvicorn connection.app:app --reload --port 8001

Then set the frontend2 base URL (frontend2/core/config.js AGENT_BASE) to match,
e.g. http://127.0.0.1:8001.

The agent library lives at team_04/agent. This package adds team_04 to sys.path
on import so `agent.*` resolves regardless of the working directory.
"""
from __future__ import annotations

import os
import sys

# team_04/ is two levels up from this file (PY/connection/ -> PY/ -> team_04/).
_TEAM_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TEAM_ROOT not in sys.path:
    sys.path.insert(0, _TEAM_ROOT)
