"""
FastAPI server — entry point for the AGENT_ui backend.
Run with:  python server.py
or:        uvicorn server:app --port 3000 --reload
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path setup — make team_03/python/ importable so adapters can use it.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]          # …/AIA26_Studio/
TEAM_03_PYTHON = REPO_ROOT / "team_03" / "python"
if str(TEAM_03_PYTHON) not in sys.path:
    sys.path.insert(0, str(TEAM_03_PYTHON))

# ---------------------------------------------------------------------------
# FastAPI + stdlib imports
# ---------------------------------------------------------------------------
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import api_routes
import mcp_bridge
import agent_runner
import isovist
from session_manager import SessionManager
from websocket_manager import ConnectionManager, MessageType

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="AGENT_ui backend", version="0.1.0")

# CORS — allow all origins for local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Shared singletons
# ---------------------------------------------------------------------------
manager = ConnectionManager()
session = SessionManager()

# Wire the session into api_routes BEFORE including the router.
api_routes.set_session(session)


def _live_layout_json() -> str:
    """The layout Grasshopper currently shows = the live workspace layout
    (team_03/workspace/session_active.json), which already includes the agent's
    placements. Used as set_observer's `layout_json` so the isovist runs on the
    real floor + obstacles. Falls back to the in-memory session layout."""
    try:
        f = Path(__file__).resolve().parents[2] / "workspace" / "session_active.json"
        if f.exists():
            return f.read_text(encoding="utf-8")
    except Exception:
        pass
    st = session.get_session() or {}
    return json.dumps(st["layout"]) if st.get("layout") else ""


def _isovist_for_point(layout_json: str, point_str) -> "list | None":
    """Compute the visibility polygon for a PERSON observer at point_str ('x,y,h')."""
    try:
        layout = json.loads(layout_json) if layout_json else None
        if not layout or not point_str:
            return None
        parts = [float(p) for p in str(point_str).split(",") if p.strip() != ""]
        if len(parts) < 2:
            return None
        x, y = parts[0], parts[1]
        h = parts[2] if len(parts) > 2 else 1.7
        return isovist.compute(layout, x, y, h)
    except Exception as exc:
        print(f"[isovist] person compute failed: {exc}")
        return None


def _isovist_for_path(layout_json: str, path_str, height) -> "list | None":
    """Compute the union isovist along a PATH ('x1,y1;x2,y2;...')."""
    try:
        layout = json.loads(layout_json) if layout_json else None
        if not layout or not path_str:
            return None
        pts = []
        for chunk in str(path_str).split(";"):
            c = [v for v in chunk.split(",") if v.strip() != ""]
            if len(c) >= 2:
                pts.append((float(c[0]), float(c[1])))
        if not pts:
            return None
        try:
            h = float(height)
        except (TypeError, ValueError):
            h = 1.7
        return isovist.compute_path(layout, pts, h)
    except Exception as exc:
        print(f"[isovist] path compute failed: {exc}")
        return None

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
app.include_router(api_routes.router)

# ---------------------------------------------------------------------------
# WebSocket endpoint  (MUST be registered BEFORE the catch-all static mount)
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    loop = asyncio.get_running_loop()
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "chat_message":
                content = data.get("content", "")
                if agent_runner.is_active():
                    # A run is in progress → feed the message to the checkpoint.
                    agent_runner.submit_decision(content)
                else:
                    # Start a new real-pipeline session for the selected layout.
                    sess = session.get_session() or {}
                    layout_name = sess.get("layout_name")
                    await agent_runner.start_session(
                        content, layout_name, manager, websocket, loop,
                    )

            elif msg_type == "chat_decision":
                # Chip click from the options panel (s1, yes, end, "rule: ...").
                agent_runner.submit_decision(str(data.get("value", "")))

            elif msg_type == "selection_sync":
                # Broadcast the selection change to all connected clients.
                await manager.broadcast(data)

            elif msg_type == "observer_point":
                # Push the draggable person point to Grasshopper via MCP (the
                # unified set_observer tool, PERSON / static visibility).
                # Use the LIVE layout GH currently shows (workspace), not the base,
                # so the isovist runs on the real floor + placed objects.
                data["layout_json"] = _live_layout_json()
                # Fails gracefully (status "error") if Swiftlet/Rhino is down.
                result = await mcp_bridge.push_observer(data)
                await manager.send_personal(
                    websocket,
                    {
                        "type": MessageType.agent_event.value,
                        "node": "set_observer",
                        "status": "completed" if result.get("status") == "ok" else "error",
                        "data": result,
                    },
                )
                # Visibility surface for the 3D viewport — computed in the backend
                # (GH's isovist is degenerate), height-aware, doors as openings.
                iso = _isovist_for_point(data["layout_json"], data.get("point_str"))
                await manager.send_personal(websocket, {
                    "type": "observer_result",
                    "mode": "person",
                    "status": result.get("status"),
                    "isovist": iso,
                })

            elif msg_type == "observer_path":
                # Unified set_observer tool, PATH mode. Use the live workspace layout.
                data["layout_json"] = _live_layout_json()
                result = await mcp_bridge.push_observer_path(data)
                await manager.send_personal(
                    websocket,
                    {
                        "type": MessageType.agent_event.value,
                        "node": "set_observer_path",
                        "status": "completed" if result.get("status") == "ok" else "error",
                        "data": result,
                    },
                )
                iso = _isovist_for_path(data["layout_json"], data.get("path_str"), data.get("height"))
                await manager.send_personal(websocket, {
                    "type": "observer_result",
                    "mode": "path",
                    "status": result.get("status"),
                    "isovist": iso,
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        # Free any agent session this client owned so the next connection
        # (e.g. a page refresh) can start a fresh run instead of routing its
        # messages into an orphaned, blocked session.
        agent_runner.abort_session(websocket)


# ---------------------------------------------------------------------------
# Static file serving for the built frontend (production mode).
# Only mount if the dist directory exists so the server still starts in dev.
# IMPORTANT: This catch-all mount MUST come AFTER all route registrations.
# ---------------------------------------------------------------------------
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")


# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=3000, reload=True)
