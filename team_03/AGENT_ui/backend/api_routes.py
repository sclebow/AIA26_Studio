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
# User / Space profile (from the onboarding screens)
# ---------------------------------------------------------------------------


class ProfilePayload(BaseModel):
    # User Profile (step 1)
    role: str = ""
    experience: str = ""
    name: str = ""
    # Space Profile (step 2) — labels already resolved by the frontend
    layoutStatus: str = ""
    workflowType: str = ""
    workflowCustom: str = ""
    spaceNotes: str = ""
    skippedSpaceAgent: bool = False


def _memory_dir() -> Path:
    """team_03/memory/ — sibling of team_03/AGENT_ui, holds the agent memory files."""
    return Path(__file__).resolve().parents[2] / "memory"


def _build_profile_md(p: ProfilePayload) -> str:
    """Render the onboarding answers as a readable, global user-memory file."""
    dash = "—"  # em dash placeholder for empty optional fields
    lines: list[str] = ["## User Profile",
                        f"- Name: {p.name.strip() or dash}",
                        f"- Role: {p.role.strip() or dash}",
                        f"- Experience: {p.experience.strip() or dash}",
                        ""]
    lines.append("## Space Profile")
    if p.skippedSpaceAgent:
        lines.append("- (skipped)")
    else:
        workflow = p.workflowCustom.strip() if p.workflowType.strip().lower() == "custom" and p.workflowCustom.strip() else p.workflowType.strip()
        lines.append(f"- Layout status: {p.layoutStatus.strip() or dash}")
        lines.append(f"- Workflow type: {workflow or dash}")
        lines.append(f"- Notes: {p.spaceNotes.strip() or dash}")
    return "\n".join(lines).strip() + "\n"


@router.post("/api/profile")
async def save_profile(body: ProfilePayload):
    """Persist the onboarding User/Space profile as a global user-memory file
    (team_03/memory/user_profile.md). Overwrites on each submit."""
    mem_dir = _memory_dir()
    mem_dir.mkdir(parents=True, exist_ok=True)
    path = mem_dir / "user_profile.md"
    path.write_text(_build_profile_md(body), encoding="utf-8")
    return {"status": "ok", "path": str(path)}


# ---------------------------------------------------------------------------
# Analysis (deterministic — no LLM / MCP needed)
# ---------------------------------------------------------------------------


class AnalyzePayload(BaseModel):
    layout: dict
    profile_config: Optional[dict] = None
    space_config: Optional[dict] = None


def _scoredata_from_scoring(sr: dict) -> dict:
    """Map nodes/scoring.py `scoring_results` → the Dashboard ScoreData shape."""
    bd = sr.get("breakdown") or {}

    def sc(tool: str) -> float:
        return round(float((bd.get(tool) or {}).get("score", 0) or 0))

    def wt(tool: str) -> float:
        return float((bd.get(tool) or {}).get("weight", 0) or 0)

    return {
        "overall": round(float(sr.get("total_score") or 0)),
        "grade": sr.get("grade") or "?",
        "collision": sc("collision"),
        "visibility": sc("visibility"),
        "path": sc("path"),
        "reachability": sc("reachability"),
        "orientation": sc("orientation"),
        "weights": {
            "collision": wt("collision"),
            "visibility": wt("visibility"),
            "path": wt("path"),
            "reachability": wt("reachability"),
            "orientation": wt("orientation"),
        },
    }


@router.post("/api/analyze")
async def analyze_layout(body: AnalyzePayload):
    """Run the 5 analysis tools + scoring on a layout and return Dashboard scores.
    Deterministic (no LLM, no Rhino/MCP) — drives the Analysis Dashboard directly."""
    from adapters.analysis_adapter import run_all

    res = run_all(body.layout, profile_config=body.profile_config, space_config=body.space_config)
    sr = res.get("scoring_results") or {}
    if sr.get("error"):
        raise HTTPException(status_code=500, detail=f"Analysis failed: {sr['error']}")
    scores = _scoredata_from_scoring(sr)
    if _session is not None:
        try:
            _session.update_scores(scores)
        except Exception:
            pass
    return scores


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


def _workspace_layout() -> Optional[dict]:
    """Read the live agent working layout (latest placements) from
    team_03/workspace/session_active.json, or None if it doesn't exist."""
    try:
        f = Path(__file__).resolve().parents[2] / "workspace" / "session_active.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


@router.post("/api/layouts/{name}/reload")
async def reload_layout(name: str):
    """
    Re-read the CURRENT working layout and update the session.

    The agent writes its placements to team_03/workspace/session_active.json, not
    the base file — so a plain re-read of the base file would drop everything the
    agent added (e.g. a newly placed desk). Prefer the workspace layout when it is
    the same layout (matching layoutId); otherwise fall back to the base file.
    Returns the fresh layout data.
    """
    base = layout_loader.load_layout(name)
    if base is None:
        raise HTTPException(status_code=404, detail=f"Layout '{name}' not found.")

    ws = _workspace_layout()
    data = ws if (ws and ws.get("layoutId") == base.get("layoutId")) else base

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
