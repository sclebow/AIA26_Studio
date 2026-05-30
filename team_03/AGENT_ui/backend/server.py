"""
FastAPI server — entry point for the AGENT_ui backend.
Run with:  python server.py
or:        uvicorn server:app --port 3000 --reload
"""
from __future__ import annotations

import asyncio
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
                # Push the draggable person point to Grasshopper via MCP.
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

            elif msg_type == "observer_path":
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
