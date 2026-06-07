"""In-memory session store.

Each session holds:
  - state          : the latest AgentState snapshot
  - history        : list of ChatMessage dicts (role, content, message_id, timestamp, tags)
  - decision_graph : DecisionGraph instance tracking the design process as a DAG
  - created_at     : ISO timestamp string

Thread-safety: uses a simple dict protected by asyncio.Lock.
Replace with Redis or a DB backend for production.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from .decision_graph import DecisionGraph


class SessionStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sessions: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(self, initial_state: dict[str, Any]) -> str:
        session_id = str(uuid.uuid4())
        async with self._lock:
            self._sessions[session_id] = {
                "state": initial_state,
                "history": [],
                "decision_graph": DecisionGraph(),
                "created_at": _now_iso(),
            }
        return session_id

    async def get(self, session_id: str) -> dict[str, Any] | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def list_ids(self) -> list[str]:
        async with self._lock:
            return list(self._sessions.keys())

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    async def get_state(self, session_id: str) -> dict[str, Any] | None:
        session = await self.get(session_id)
        return session["state"] if session else None

    async def update_state(self, session_id: str, state: dict[str, Any]) -> None:
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["state"] = state

    # ------------------------------------------------------------------
    # Chat history
    # ------------------------------------------------------------------

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tags: list[str] | None = None,
    ) -> str:
        message_id = str(uuid.uuid4())
        msg = {
            "role": role,
            "content": content,
            "message_id": message_id,
            "timestamp": _now_iso(),
            "tags": tags or [],
        }
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["history"].append(msg)
        return message_id

    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        session = await self.get(session_id)
        return session["history"] if session else []

    # ------------------------------------------------------------------
    # Decision graph
    # ------------------------------------------------------------------

    async def get_graph(self, session_id: str) -> DecisionGraph | None:
        session = await self.get(session_id)
        if session is None:
            return None
        return session.get("decision_graph") or DecisionGraph()

    async def save_graph(self, session_id: str, graph: DecisionGraph) -> None:
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["decision_graph"] = graph


# Module-level singleton used by all routers
store = SessionStore()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
