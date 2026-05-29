"""
MCP bridge for the AGENT_ui backend.

Lets the web UI push lightweight commands (e.g. the draggable observer point)
straight to Grasshopper via Swiftlet, reusing the existing HTTP JSON-RPC client
from team_03/python/_runtime/. The agent pipeline (main.py) keeps its own client;
this is an independent, lazily-connected client owned by the UI backend.

server.py inserts team_03/python on sys.path, so the imports below resolve.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from _runtime.mcp_client import McpClient
from _runtime.config import _load_mcp_server_from_json

# Short timeout — set_observer just draws a point, it should return fast.
_OBSERVER_TIMEOUT_SECONDS = 30.0

_client: Optional[McpClient] = None
_endpoint: Optional[str] = None
_lock = asyncio.Lock()


def _repo_root() -> Path:
    # …/AIA26_Studio/team_03/AGENT_ui/backend/mcp_bridge.py → AIA26_Studio/
    return Path(__file__).resolve().parents[3]


def _resolve_endpoint() -> str:
    global _endpoint
    if _endpoint is None:
        _, _endpoint = _load_mcp_server_from_json(_repo_root() / "mcp.json")
    return _endpoint


def _ensure_client() -> McpClient:
    """Build + initialize the MCP client on first use (synchronous)."""
    global _client
    if _client is None:
        client = McpClient(_resolve_endpoint(), _OBSERVER_TIMEOUT_SECONDS)
        client.initialize()
        _client = client
    return _client


def _call_set_observer_sync(point_str: str, height: float) -> Dict[str, Any]:
    """Blocking MCP call — runs in a thread executor."""
    try:
        client = _ensure_client()
        raw = client.call_tool(
            "set_observer",
            {"point": point_str, "height": height},
            timeout=_OBSERVER_TIMEOUT_SECONDS,
        )
        return {"status": "ok", "tool": "set_observer", "point": point_str, "raw": raw}
    except Exception as exc:  # Swiftlet down, tool missing, timeout, etc.
        # Reset the client so the next attempt reconnects cleanly.
        global _client
        _client = None
        return {"status": "error", "tool": "set_observer", "point": point_str, "message": str(exc)}


def _call_set_observer_path_sync(path_str: str, height: float) -> Dict[str, Any]:
    """Blocking MCP call for a multi-point path — runs in a thread executor."""
    try:
        client = _ensure_client()
        raw = client.call_tool(
            "set_observer_path",
            {"path_points": path_str, "height": height},
            timeout=_OBSERVER_TIMEOUT_SECONDS,
        )
        return {"status": "ok", "tool": "set_observer_path", "path_str": path_str, "raw": raw}
    except Exception as exc:
        global _client
        _client = None
        return {"status": "error", "tool": "set_observer_path", "path_str": path_str, "message": str(exc)}


async def push_observer_path(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Push an observer path to Grasshopper via MCP.

    `data` is the parsed `observer_path` WS message:
        { type, path_str, height }
    Returns a status dict (never raises) so the WS loop stays alive even when
    Swiftlet/Rhino is not running.
    """
    path_str = data.get("path_str")
    if not isinstance(path_str, str) or not path_str.strip():
        return {"status": "error", "tool": "set_observer_path", "message": "missing path_str"}

    try:
        height = float(data.get("height", 1.7))
    except (TypeError, ValueError):
        height = 1.7

    async with _lock:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _call_set_observer_path_sync, path_str, height)


async def push_observer(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Push an observer point to Grasshopper via MCP.

    `data` is the parsed `observer_point` WS message:
        { type, x, y, height, point_str }
    Returns a status dict (never raises) so the WS loop stays alive even when
    Swiftlet/Rhino is not running.
    """
    point_str = data.get("point_str")
    if not isinstance(point_str, str) or not point_str.strip():
        # Fall back to composing from x/y/height if the string is missing.
        x = data.get("x")
        y = data.get("y")
        h = data.get("height", 1.7)
        if x is None or y is None:
            return {"status": "error", "tool": "set_observer", "message": "missing point_str / x,y"}
        point_str = f"{float(x):.2f},{float(y):.2f},{float(h):.2f}"

    try:
        height = float(data.get("height", 1.7))
    except (TypeError, ValueError):
        height = 1.7

    # httpx.Client is synchronous → run off the event loop, serialized by a lock
    # so concurrent releases don't race on the lazy client init.
    async with _lock:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _call_set_observer_sync, point_str, height)
