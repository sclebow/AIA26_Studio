"""Team 04 FastAPI backend.

Start with:
    cd team_04/backend
    uvicorn app:app --reload --port 8000

Or from repo root:
    uvicorn team_04.backend.app:app --reload --port 8000

API docs: http://localhost:8000/docs
"""
from __future__ import annotations

import sys
import os

# Ensure team_04/ parent is on the path so `agent.*` imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import sessions, chat, explorer, tools, decisions

app = FastAPI(
    title="AIA26 Studio — Team 04 API",
    description=(
        "Building placement + view analysis backend.\n\n"
        "- **/sessions** — create/list/delete agent sessions\n"
        "- **/sessions/{id}/chat** — SSE streaming chat with the LangGraph agent\n"
        "- **/sessions/{id}/explorer** — site + building tree for the UI explorer panel\n"
        "- **/tools** — direct tool invocation (view analysis, optimizers, setbacks)\n"
    ),
    version="0.1.0",
)

# Allow the React/Vue frontend on any origin in dev; tighten for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(explorer.router)
app.include_router(tools.router)
app.include_router(decisions.router)


@app.get("/", tags=["health"])
async def root() -> dict:
    return {
        "status": "ok",
        "service": "AIA26 Studio Team 04",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
