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
from agent_runner import run_agent
from session_manager import SessionManager
from websocket_manager import ConnectionManager

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
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "chat_message":
                # Run agent pipeline in background so the WS loop stays responsive.
                asyncio.create_task(
                    run_agent(
                        data.get("content", ""),
                        session.get_session(),
                        manager,
                        websocket,
                        session=session,
                    )
                )

            elif msg_type == "selection_sync":
                # Broadcast the selection change to all connected clients.
                await manager.broadcast(data)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


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
