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
import layout_generator
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
# LLM config (pipeline provider toggle)
# ---------------------------------------------------------------------------


@router.get("/api/llm-config")
async def get_llm_config():
    """Active pipeline provider/model + selectable models + which providers have
    credentials, so the UI can render the provider toggle synced to the real .env
    and dim a provider whose API key is missing.
    """
    import os

    from _runtime.config import load_settings, _repo_root
    from pipeline_bridge import (
        PIPELINE_MODELS,
        get_pipeline_provider,
        get_pipeline_model,
    )

    settings = load_settings()  # also (re)loads .env into os.environ
    provider = get_pipeline_provider() or settings.llm_provider
    model = get_pipeline_model() or settings.llm_model

    return {
        "provider": provider,
        "model": model,
        "available": PIPELINE_MODELS,
        "credentials": {
            "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "google": bool(os.environ.get("GOOGLE_API_KEY")),
        },
        "envPath": str(_repo_root() / ".env"),
    }


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


@router.get("/api/layouts/{name}/versions", response_model=List[Dict[str, Any]])
async def get_layout_versions(name: str):
    """Return the version history for a base layout: the original plus every
    approved revision saved to team_03/output/, oldest → newest."""
    return layout_loader.list_versions(name)


class VersionSelect(BaseModel):
    version_id: str          # base name (original) or output file stem (version)
    file: Optional[str] = None  # output file name for a revision (None = original)


@router.post("/api/layouts/{name}/version/select")
async def select_layout_version(name: str, body: VersionSelect):
    """Make a specific version of *name* the active working layout.

    Loads the version JSON (the original base layout, or a revision file from
    team_03/output/), mirrors it into the live workspace session, rebuilds the
    spatial graph, and PINS it so the next chat run operates on this revision
    instead of the base file. Returns the layout JSON for the viewport."""
    if body.file:
        data = layout_loader.load_version(body.file)
        is_original = False
    else:
        data = layout_loader.load_layout(name)
        is_original = True
    if data is None:
        raise HTTPException(status_code=404, detail=f"Version '{body.version_id}' not found.")

    # Live workspace file (Grasshopper / observer / reload all read this).
    _write_session_active(data)

    if _session is not None:
        _session.update_layout(data)
        try:
            graph_data = build_graph(data)
            if "error" not in graph_data:
                _session.update_graph(graph_data)
        except Exception:
            pass

    # Pin so the chat pipeline runs on the chosen revision. Selecting the
    # original clears the pin (build_context falls back to the base file).
    try:
        import pipeline_bridge
        pipeline_bridge.set_pinned_layout(None if is_original else name, None if is_original else data)
    except Exception:
        pass

    # The user switched the working layout under any in-flight chat run — abort
    # it so the next message rebuilds the pipeline on the selected revision.
    try:
        import agent_runner
        agent_runner.abort_session()
    except Exception:
        pass

    return data


@router.delete("/api/layouts/{name}/versions/{file_name}")
async def delete_layout_version(name: str, file_name: str):
    """Delete a specific revision from team_03/output/.

    Only files whose stem starts with the base layout name are accepted
    (path-traversal and cross-layout deletes are rejected with 400).
    The original base layout can never be deleted through this endpoint."""
    safe = Path(file_name).name          # strip any directory component
    if not safe.endswith(".json"):
        safe += ".json"
    stem = Path(safe).stem

    # Guard: must belong to this base layout and be a timestamped revision.
    if not stem.startswith(f"{name}_"):
        raise HTTPException(status_code=400, detail="File does not belong to this layout.")

    out = layout_loader._output_dir()
    target = out / safe
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Version file '{safe}' not found.")

    try:
        target.unlink()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not delete file: {exc}") from exc

    return {"status": "ok", "deleted": safe}


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
# AI Layout Generator (Sonnet — independent of the chat pipeline's Haiku policy)
# ---------------------------------------------------------------------------


class ProgramItem(BaseModel):
    name: str
    count: int = 1


class GenerateLayoutPayload(BaseModel):
    layoutType: str = "residential"
    areaMin: float = 0.0
    areaMax: float = 0.0
    programs: List[ProgramItem] = []
    brief: str = ""
    variantIndex: int = 0


@router.post("/api/layouts/generate")
async def generate_layout(body: GenerateLayoutPayload):
    """Generate ONE layout with Anthropic Sonnet from the panel's form.

    Returns {"layout": <LayoutJSON>}. The frontend calls this once per "Generate"
    click and accumulates results into its in-memory library (max 4)."""
    req = {
        "layoutType": body.layoutType,
        "areaMin": body.areaMin,
        "areaMax": body.areaMax,
        "programs": [p.model_dump() for p in body.programs],
        "brief": body.brief,
    }
    try:
        layout = await layout_generator.generate_one(req, body.variantIndex)
    except RuntimeError as exc:
        # Configuration problems (e.g. missing API key) → 503.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # parse / validation / model errors
        raise HTTPException(status_code=502, detail=f"Layout generation failed: {exc}") from exc
    return {"layout": layout}


class SaveGeneratedPayload(BaseModel):
    name: str
    layout: dict


@router.post("/api/layouts/generated/save")
async def save_generated(body: SaveGeneratedPayload):
    """Persist an accepted generated layout to team_03/layout/AI_GENERATED/<name>.json
    so it shows up in the Layout Loader dropdown under the 'AI_GENERATED' group."""
    layout = dict(body.layout)
    if not layout_loader.validate_layout(layout):
        raise HTTPException(status_code=422, detail="Invalid layout JSON.")

    stem = layout_loader._sanitize_name(body.name)
    layout["layoutId"] = stem  # keep id stable / matching the saved file name
    path = layout_loader.save_generated_layout(stem, layout)
    return {
        "status": "ok",
        "name": stem,
        "path": str(path),
        "category": path.parent.name,
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


@router.delete("/api/memory")
async def clear_memory():
    """Delete ALL agent memory files (team_03/memory/*.md): the onboarding
    user_profile and every per-layout rules file. The agent then starts fresh
    (no learned rules / preferences) on the next chat run."""
    mem_dir = _memory_dir()
    deleted: List[str] = []
    if mem_dir.exists():
        for f in mem_dir.glob("*.md"):
            try:
                f.unlink()
                deleted.append(f.name)
            except Exception:
                pass
    return {"status": "ok", "deleted": deleted, "count": len(deleted)}


# ---------------------------------------------------------------------------
# Analysis (deterministic — no LLM / MCP needed)
# ---------------------------------------------------------------------------


class AnalyzePayload(BaseModel):
    layout: dict
    profile_config: Optional[dict] = None
    space_config: Optional[dict] = None
    tool: Optional[str] = None  # "collision" | "path" | "visibility" — run only one tool


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
    """Run analysis tools on a layout.

    When `tool` is set, runs ONLY that tool and returns its overlay data.
    When omitted, runs all 5 tools + scoring (used by the agent pipeline)."""
    from adapters.analysis_adapter import (
        run_collision, run_path_analysis, run_visibility, run_all,
    )

    tool = (body.tool or "").strip().lower()

    # ── Single-tool path (toggled from the Dashboard) ──────────────────────
    if tool == "collision":
        result = run_collision(body.layout, profile_config=body.profile_config)
        response: dict = {}
        gv = result.get("grid_viz")
        if gv:
            response["collision_overlay"] = gv
        return response

    if tool == "path":
        result = run_path_analysis(body.layout)
        return {"path_result": result}

    if tool == "visibility":
        result = run_visibility(body.layout)
        return {"visibility_result": result}

    # ── Full analysis (all 5 tools + scoring) ──────────────────────────────
    res = run_all(body.layout, profile_config=body.profile_config, space_config=body.space_config)
    sr = res.get("scoring_results") or {}
    if sr.get("error"):
        raise HTTPException(status_code=500, detail=f"Analysis failed: {sr['error']}")
    scores = _scoredata_from_scoring(sr)

    collision_r = res.get("collision_results") or {}
    gv = collision_r.get("grid_viz")
    if gv:
        scores["collision_overlay"] = gv

    orientation_r = res.get("orientation_results") or {}
    orient_results = orientation_r.get("results", [])
    if orient_results:
        scores["orientation_overlay"] = {"results": orient_results}

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


def _write_session_active(data: dict) -> None:
    """Mirror the selected layout into team_03/workspace/session_active.json — the
    LIVE working layout that Grasshopper, the observer (set_observer) and the
    /reload endpoint all read. Selecting a layout in the dropdown must update this
    file; otherwise GH and the chat keep running on the previously loaded plan
    (it is only rewritten by the chat pipeline's build_context otherwise)."""
    try:
        f = Path(__file__).resolve().parents[2] / "workspace" / "session_active.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


@router.post("/api/session")
async def create_session(body: SessionCreate):
    """Create a new session by loading the named layout and building the graph.

    Picking a layout in the dropdown (incl. AI-generated) also: (a) mirrors it into
    the live workspace file Grasshopper/observer/reload use, and (b) resets any
    in-flight chat run when the layout changes, so the next message rebuilds the
    pipeline on the newly-selected layout instead of the previous one."""
    if _session is None:
        raise HTTPException(status_code=500, detail="Session manager not initialised.")

    prev = _session.get_session()
    prev_name = prev.get("layout_name") if prev else None

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

    # Make the selected layout the live working layout (Grasshopper / observer / reload).
    _write_session_active(data)

    # Picking a base layout in the dropdown resets the version selection to its
    # "current" state — clear any pinned revision so the chat runs on the base.
    try:
        import pipeline_bridge
        pipeline_bridge.set_pinned_layout(None, None)
    except Exception:
        pass

    # If the layout actually changed, abort any active chat session so the next
    # message starts fresh on the new layout (build_context re-copies it).
    if body.layout_name != prev_name:
        try:
            import agent_runner
            agent_runner.abort_session()
        except Exception:
            pass

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
        # Try to build the graph on-the-fly from the current layout
        layout = state.get("layout")
        if layout:
            graph_data = build_graph(layout)
            if "error" not in graph_data:
                _session.update_graph(graph_data)
                return graph_data
            # Surface the error so it's visible in the frontend console
            return JSONResponse(content={"error": graph_data.get("error", "unknown build error")})
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
        # Rebuild the spatial graph so newly placed objects + their relations
        # (near / contained_in / blocks …) show up in the Spatial Graph panel.
        # Without this the graph stays frozen at the base layout while the agent
        # populates the floor.
        try:
            graph_data = build_graph(data)
            if "error" not in graph_data:
                _session.update_graph(graph_data)
        except Exception:
            pass

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


# ---------------------------------------------------------------------------
# Benchmarks — recorded pipeline runs + per-model aggregates
# ---------------------------------------------------------------------------


@router.get("/api/benchmarks")
async def get_benchmarks():
    """All recorded pipeline runs (newest first) + per-model aggregates.

    Each chat session is auto-recorded by `agent_runner` (provider/model, per-node
    timings, reason turns, API-call breakdown, recursion hits, scoring breakdown).
    Drives the Benchmark dashboard's workflow + score-trend + model-comparison
    modules."""
    import benchmark
    return benchmark.get_all()


@router.delete("/api/benchmarks")
async def clear_benchmarks():
    """Delete the entire benchmark history (team_03/AGENT_ui/backend/benchmarks/)."""
    import benchmark
    removed = benchmark.clear_all()
    return {"status": "ok", "removed": removed}


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
