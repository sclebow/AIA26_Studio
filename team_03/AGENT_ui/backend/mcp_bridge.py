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
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

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


# Keys under which the GH "cluster results" might return the isovist polygon.
_ISOVIST_KEYS = ("isovist", "boundary", "visibility", "visibility_polygon", "polygon", "surface", "points")


def _coerce_polygon(value: Any) -> Optional[List[List[float]]]:
    """Return [[x,y], …] (>=3 pts) if *value* is a list of [x,y(,z)] pairs, else None."""
    if not isinstance(value, list) or len(value) < 3:
        return None
    out: List[List[float]] = []
    for p in value:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                out.append([float(p[0]), float(p[1])])
            except (TypeError, ValueError):
                return None
        else:
            return None
    return out if len(out) >= 3 else None


def _extract_isovist(raw: str) -> Optional[List[List[float]]]:
    """Tolerant parse of the set_observer response: find the first [[x,y],…] polygon
    under a known key (or a bare polygon). Returns layout-metre points or None.
    The exact key/shape is confirmed from the logged raw on the first live run."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        data = json.loads(raw.strip())
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None

    direct = _coerce_polygon(data)
    if direct:
        return direct

    def _search(obj: Any) -> Optional[List[List[float]]]:
        if isinstance(obj, dict):
            for k in _ISOVIST_KEYS:
                if k in obj:
                    p = _coerce_polygon(obj[k])
                    if p:
                        return p
            for v in obj.values():
                p = _search(v)
                if p:
                    return p
        elif isinstance(obj, list):
            p = _coerce_polygon(obj)
            if p:
                return p
            for v in obj:
                p = _search(v)
                if p:
                    return p
        return None

    return _search(data)


def _call_set_observer_sync(
    point_str: str, height: float, layout_json: str, path_str: str
) -> Dict[str, Any]:
    """Blocking MCP call to the unified `set_observer` tool — runs in a thread
    executor. All arguments are passed as strings to match the tool schema
    (Define Tool Parameter → type "string"). An empty `path_points` means PERSON
    (static visibility at `point`); a non-empty one means PATH (traverse + analyze).
    """
    mode = "path" if path_str else "person"
    try:
        client = _ensure_client()
        raw = client.call_tool(
            "set_observer",
            {
                "point": point_str,
                "height": f"{height:.2f}",
                "layout_json": layout_json or "",
                "path_points": path_str or "",
            },
            timeout=_OBSERVER_TIMEOUT_SECONDS,
        )
        print(f"[observer] set_observer ({mode}) raw: {str(raw)[:500]}")
        isovist = _extract_isovist(raw)

        # set_observer's output REPLACES the Grasshopper/Rhino preview, hiding the
        # floor the agent drew. Redraw the live (populated) layout right after so it
        # stays visible in Rhino. Best-effort — a missing set_viewport must not fail.
        if layout_json:
            try:
                client.call_tool(
                    "set_viewport",
                    {"layout_json": layout_json, "mode": "all"},
                    timeout=_OBSERVER_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                print(f"[observer] set_viewport (restore layout) failed: {exc}")
        return {"status": "ok", "tool": "set_observer", "mode": mode,
                "point": point_str, "path_str": path_str, "raw": raw, "isovist": isovist}
    except Exception as exc:  # Swiftlet down, tool missing, timeout, etc.
        # Reset the client so the next attempt reconnects cleanly.
        global _client
        _client = None
        return {"status": "error", "tool": "set_observer", "mode": mode,
                "point": point_str, "path_str": path_str, "message": str(exc)}


def _first_path_point(path_str: str, height: float) -> str:
    """Return the first path vertex as a "x,y,h" point string (the unified tool's
    `point` param is still provided in PATH mode)."""
    first = path_str.split(";", 1)[0].strip()
    coords = [c.strip() for c in first.split(",") if c.strip()]
    if len(coords) >= 2:
        return f"{coords[0]},{coords[1]},{height:.2f}"
    return ""


async def push_observer_path(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Push an observer PATH to Grasshopper via the unified `set_observer` tool.

    `data` is the parsed `observer_path` WS message + injected layout:
        { type, path_str, height, layout_json }
    Returns a status dict (never raises) so the WS loop stays alive even when
    Swiftlet/Rhino is not running.
    """
    path_str = data.get("path_str")
    if not isinstance(path_str, str) or not path_str.strip():
        return {"status": "error", "tool": "set_observer", "mode": "path", "message": "missing path_str"}

    try:
        height = float(data.get("height", 1.7))
    except (TypeError, ValueError):
        height = 1.7

    layout_json = data.get("layout_json", "") or ""
    point_str = _first_path_point(path_str, height)

    async with _lock:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _call_set_observer_sync, point_str, height, layout_json, path_str
        )


async def push_observer(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Push an observer POINT (PERSON / static visibility) to Grasshopper via the
    unified `set_observer` tool (empty `path_points`).

    `data` is the parsed `observer_point` WS message + injected layout:
        { type, x, y, height, point_str, layout_json }
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
            return {"status": "error", "tool": "set_observer", "mode": "person", "message": "missing point_str / x,y"}
        point_str = f"{float(x):.2f},{float(y):.2f},{float(h):.2f}"

    try:
        height = float(data.get("height", 1.7))
    except (TypeError, ValueError):
        height = 1.7

    layout_json = data.get("layout_json", "") or ""

    # httpx.Client is synchronous → run off the event loop, serialized by a lock
    # so concurrent releases don't race on the lazy client init.
    async with _lock:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _call_set_observer_sync, point_str, height, layout_json, ""
        )
