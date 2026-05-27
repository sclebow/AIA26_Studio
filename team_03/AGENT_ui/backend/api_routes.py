"""
REST API routes for layout management and session control.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import layout_loader
from session_manager import SessionManager
from adapters.graph_adapter import build_graph

router = APIRouter()

# Shared session instance (injected by server.py at startup).
_session: Optional[SessionManager] = None


def set_session(session: SessionManager) -> None:
    """Called by server.py to wire in the shared SessionManager."""
    global _session
    _session = session


# ---------------------------------------------------------------------------
# Layouts
# ---------------------------------------------------------------------------


@router.get("/api/layouts", response_model=List[Dict[str, Any]])
async def get_layouts():
    """Return all layout JSON files found under team_03/layout/."""
    return layout_loader.list_layouts()


@router.get("/api/layouts/{name}")
async def get_layout(name: str):
    """Load a specific layout by stem name (e.g. 'industrial_005')."""
    data = layout_loader.load_layout(name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Layout '{name}' not found.")
    return data


@router.post("/api/layouts/upload")
async def upload_layout(file: UploadFile = File(...)):
    """
    Accept an uploaded JSON layout file.
    Validates that it contains the required keys (layoutId, outline, rooms).
    Returns the parsed layout data.
    """
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="File must be a .json file.")

    raw = await file.read()
    try:
        data: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    if not layout_loader.validate_layout(data):
        raise HTTPException(
            status_code=422,
            detail="Layout JSON missing required keys: layoutId, outline, rooms.",
        )

    # Save to a temp file so callers have a path reference if needed.
    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=".json", prefix="upload_"
    )
    tmp.write(raw)
    tmp.close()

    return {
        "status": "ok",
        "tmp_path": tmp.name,
        "name": Path(file.filename).stem,
        "layout": data,
    }


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    layout_name: str


@router.get("/api/session")
async def get_session():
    """Return the current session state (layout, graph, scores) or null."""
    if _session is None:
        return JSONResponse(content=None)
    state = _session.get_session()
    return JSONResponse(content=state)


@router.post("/api/session")
async def create_session(body: SessionCreate):
    """Create a new session by loading the named layout and building the graph."""
    if _session is None:
        raise HTTPException(status_code=500, detail="Session manager not initialised.")

    data = layout_loader.load_layout(body.layout_name)
    if data is None:
        raise HTTPException(
            status_code=404, detail=f"Layout '{body.layout_name}' not found."
        )

    state = _session.create_session(body.layout_name, data)

    # Auto-build the spatial graph from the layout
    graph_data = build_graph(data)
    if "error" not in graph_data:
        _session.update_graph(graph_data)
        state["graph"] = graph_data

    return state


# ---------------------------------------------------------------------------
# Graph & Scores
# ---------------------------------------------------------------------------


@router.get("/api/graph")
async def get_graph():
    """Return the current spatial graph as node-link JSON."""
    if _session is None:
        raise HTTPException(status_code=500, detail="Session manager not initialised.")
    state = _session.get_session()
    if state is None:
        raise HTTPException(status_code=404, detail="No active session.")
    graph = state.get("graph")
    if graph is None:
        return JSONResponse(content=None)
    return graph


@router.post("/api/layouts/{name}/reload")
async def reload_layout(name: str):
    """
    Re-read the layout JSON from disk and update the session.
    Use this after the agent has modified the layout file externally.
    Returns the fresh layout data.
    """
    data = layout_loader.load_layout(name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Layout '{name}' not found.")

    if _session is not None:
        _session.update_layout(data)

    return data


class LayoutCommit(BaseModel):
    layout: dict


@router.post("/api/layouts/{name}/commit")
async def commit_layout(name: str, body: LayoutCommit):
    """
    Write an accepted (previously proposed) layout to disk,
    replacing the existing layout file. Updates the session state.
    """
    if not layout_loader.validate_layout(body.layout):
        raise HTTPException(status_code=422, detail="Invalid layout JSON.")

    saved = layout_loader.save_layout(name, body.layout)
    if saved is None:
        raise HTTPException(
            status_code=404, detail=f"Layout '{name}' not found on disk."
        )

    if _session is not None:
        _session.update_layout(body.layout)
        _session.clear_pending()

    return {"status": "ok", "path": str(saved)}


@router.get("/api/scores")
async def get_scores():
    """Return the current scoring results."""
    if _session is None:
        raise HTTPException(status_code=500, detail="Session manager not initialised.")
    state = _session.get_session()
    if state is None:
        raise HTTPException(status_code=404, detail="No active session.")
    scores = state.get("scores")
    if scores is None:
        return JSONResponse(content=None)
    return scores
