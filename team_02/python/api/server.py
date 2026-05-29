"""
server.py — FastAPI backend for Sensi. Web replacement for the QWebChannel bridge.

Run (from python/):
    uvicorn api.server:app --reload --port 8000
or:
    python -m api.server

Every endpoint mirrors a SensiBridge slot. State that used to live on the single
bridge instance (self._session, self._inspire) now lives in an in-memory store
keyed by session_id, so a shared link can serve more than one visitor. Per-session
durable storage is a Phase 7 (production) concern, not handled here.

The agent context (LLM clients + local comfort tools) is built once at startup.
"""

from __future__ import annotations

import json
import queue
import re as _re
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import os
import sys

# Make python/ importable whether launched as `python -m api.server` or uvicorn.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _runtime.bootstrap import bootstrap
from graph import run_agent
from inspire import run_inspire_round, profile_chat_reply
from api import contracts

# persona.json lives at team_02/personas/persona.json (matches the PyQt app).
_PERSONA_PATH = Path(__file__).resolve().parent.parent.parent / "personas" / "persona.json"


# ═══════════════════════════════════════════════════════════════════════════════
# App + CORS
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="Sensi API", version="0.1.0")

_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Agent context (built once) + per-session state store
# ═══════════════════════════════════════════════════════════════════════════════

_CTX: Any = None


@app.on_event("startup")
def _startup() -> None:
    global _CTX
    print("[api] Bootstrapping backend...")
    _CTX = bootstrap()
    print("[api] Backend ready.")


def _fresh_inspire() -> dict:
    return {"analysis": "", "text": "", "b64s": [],
            "r1_picks": [], "r2_picks": [], "final_picks": []}


# session_id -> {"session": dict, "inspire": dict}
_STORE: dict[str, dict] = {}


def _slot(session_id: Optional[str]) -> tuple[str, dict]:
    """Return (session_id, slot), creating a new slot if needed."""
    sid = session_id or uuid.uuid4().hex
    slot = _STORE.get(sid)
    if slot is None:
        slot = {"session": {}, "inspire": _fresh_inspire()}
        _STORE[sid] = slot
    return sid, slot


def _read_persona() -> Optional[dict]:
    if _PERSONA_PATH.exists():
        try:
            return json.loads(_PERSONA_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Request models
# ═══════════════════════════════════════════════════════════════════════════════

class SessionReq(BaseModel):
    session_id: Optional[str] = None

class MessageReq(SessionReq):
    text: str

class PrepareInspireReq(SessionReq):
    text: str = ""
    b64s: list[str] = []
    round: int = 1

class RefineInspireReq(SessionReq):
    refine_desc: str = ""
    round: int = 2

class PicksReq(SessionReq):
    round: int
    urls: list[str] = []

class MoodboardReq(SessionReq):
    sense_counts: dict[str, int] = {}

class ProfileChatReq(SessionReq):
    text: str

class LayoutSelectReq(BaseModel):
    session_id: Optional[str] = None
    layout_id: str

class LayoutUploadReq(BaseModel):
    session_id: Optional[str] = None
    layout_json: str


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints — ALL routes must be registered before app.mount("/", ...)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "ready": _CTX is not None}


@app.post("/api/init")
def init(req: SessionReq) -> dict:
    """Initialise a session. Mirrors SensiBridge.initApp."""
    sid, slot = _slot(req.session_id)
    persona = _read_persona()
    if persona:
        slot["session"] = contracts.session_for_returning_user(persona)
        payload = contracts.init_payload_from_persona(persona)
    else:
        message, new_session = run_agent("", _CTX, {})
        slot["session"] = new_session
        payload = contracts.init_payload_from_greeting(message, new_session)
    return {"session_id": sid, **payload}


@app.post("/api/message")
def message(req: MessageReq) -> dict:
    """Run one agent turn. Mirrors SensiBridge.sendMessage."""
    sid, slot = _slot(req.session_id)
    msg, new_session = run_agent(req.text, _CTX, slot["session"])
    slot["session"] = new_session
    return {"session_id": sid, **contracts.agent_response_payload(msg, new_session, new_session)}


@app.post("/api/reset-persona")
def reset_persona(req: SessionReq) -> dict:
    """Delete persona.json and restart onboarding. Mirrors SensiBridge.resetPersona."""
    if _PERSONA_PATH.exists():
        _PERSONA_PATH.unlink()
    sid, slot = _slot(req.session_id)
    slot["session"] = {}
    slot["inspire"] = _fresh_inspire()
    message, new_session = run_agent("", _CTX, {})
    slot["session"] = new_session
    return {"session_id": sid, **contracts.init_payload_from_greeting(message, new_session)}


def _inspire_stream(slot: dict, sid: str, *, text: str, b64s: list,
                    round_num: int, refine_desc: str = "") -> StreamingResponse:
    """Run an inspire round in a worker thread; stream progress + result as SSE."""
    insp = slot["inspire"]
    if not refine_desc:
        insp["text"] = text
        insp["b64s"] = b64s
    llm = _CTX.llm_simple
    q: "queue.Queue[tuple[str, Any]]" = queue.Queue()

    def worker() -> None:
        res = run_inspire_round(
            llm,
            insp["text"],
            insp["b64s"],
            insp["analysis"],
            round_num,
            refine_desc=refine_desc,
            progress=lambda m: q.put(("progress", m)),
        )
        if res.get("ok"):
            insp["analysis"] = res.get("analysis", insp["analysis"])
        q.put(("result", res))

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        yield f"event: session\ndata: {json.dumps({'session_id': sid})}\n\n"
        while True:
            kind, payload = q.get()
            if kind == "progress":
                yield f"event: progress\ndata: {json.dumps({'message': payload})}\n\n"
            else:
                yield f"event: result\ndata: {json.dumps(payload)}\n\n"
                break

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/inspire/prepare")
def inspire_prepare(req: PrepareInspireReq) -> StreamingResponse:
    sid, slot = _slot(req.session_id)
    return _inspire_stream(slot, sid, text=req.text, b64s=req.b64s, round_num=req.round)


@app.post("/api/inspire/refine")
def inspire_refine(req: RefineInspireReq) -> StreamingResponse:
    sid, slot = _slot(req.session_id)
    return _inspire_stream(slot, sid, text="", b64s=[],
                           round_num=req.round, refine_desc=req.refine_desc)


@app.post("/api/inspire/picks")
def inspire_picks(req: PicksReq) -> dict:
    sid, slot = _slot(req.session_id)
    key = {1: "r1_picks", 2: "r2_picks", 3: "final_picks"}.get(req.round, "final_picks")
    slot["inspire"][key] = req.urls
    return {"session_id": sid, "ok": True}


@app.post("/api/inspire/moodboard")
def inspire_moodboard(req: MoodboardReq) -> dict:
    sid, slot = _slot(req.session_id)
    insp = slot["inspire"]
    sess = slot["session"]

    all_picks = list(dict.fromkeys(
        insp["r1_picks"] + insp["r2_picks"] + insp["final_picks"]
    ))

    sess["inspire_image_analysis"] = insp["analysis"]
    sess["inspire_moodboard_urls"] = all_picks
    sess["inspire_sense_picks"]    = req.sense_counts or {}
    sess["inspire_prompted"]       = True

    context = contracts.moodboard_context(
        sess.get("user_name", ""), insp["text"], len(all_picks)
    )

    message, new_session = run_agent(context, _CTX, sess)
    slot["session"] = new_session
    persona = contracts.patch_persona(new_session)

    return {
        "session_id":     sid,
        "persona":        persona,
        "moodboard_urls": all_picks[:6],
        "message":        message,
    }


@app.post("/api/layout")
def layout(req: SessionReq) -> dict:
    """Return the current session's layout JSON for the in-UI 2D/3D viewer."""
    sid, slot = _slot(req.session_id)
    raw = slot["session"].get("layout_json_string", "")
    layout_obj = None
    if raw:
        try:
            layout_obj = json.loads(raw)
        except Exception:
            layout_obj = None
    return {
        "session_id": sid,
        "layout": layout_obj,
        "layout_id": slot["session"].get("layout_id"),
    }


@app.post("/api/layout/select")
def layout_select(req: LayoutSelectReq) -> dict:
    """Select a named layout by ID. Stores layout_id on session so next agent turn loads it."""
    sid, slot = _slot(req.session_id)
    slot["session"]["layout_id"] = req.layout_id
    slot["session"]["last_scores_json"] = ""
    slot["session"]["last_conflicts_json"] = ""
    slot["session"]["last_suggestions_json"] = ""
    slot["session"]["layout_json_string"] = ""
    return {"session_id": sid, "ok": True, "layout_id": req.layout_id}


@app.post("/api/layout/upload")
def layout_upload(req: LayoutUploadReq) -> dict:
    """Upload a custom layout JSON. Saves to randomized_layouts/ and selects it."""
    sid, slot = _slot(req.session_id)
    try:
        data = json.loads(req.layout_json)
    except Exception:
        return {"session_id": sid, "ok": False, "error": "Invalid JSON"}

    layout_id = str(data.get("layoutId", f"custom-{sid[:6]}"))
    layout_id = _re.sub(r"[^a-zA-Z0-9\-]", "-", layout_id)

    layouts_dir = _CTX.layout_input_dir if _CTX else (
        Path(__file__).resolve().parent.parent.parent / "randomized_layouts"
    )
    save_path = layouts_dir / f"layout_{layout_id}.json"
    try:
        save_path.write_text(req.layout_json, encoding="utf-8")
    except Exception as exc:
        return {"session_id": sid, "ok": False, "error": str(exc)}

    slot["session"]["layout_id"] = layout_id
    slot["session"]["last_scores_json"] = ""
    slot["session"]["last_conflicts_json"] = ""
    slot["session"]["last_suggestions_json"] = ""
    slot["session"]["layout_json_string"] = ""

    return {"session_id": sid, "ok": True, "layout_id": layout_id, "name": data.get("name", layout_id)}


@app.post("/api/profile-chat")
def profile_chat(req: ProfileChatReq) -> dict:
    """Profile-review chat (direct LLM, no graph). Mirrors SensiBridge.profileChat."""
    sid, slot = _slot(req.session_id)
    profile = slot["session"].get("persona_profile") or {}
    result = profile_chat_reply(_CTX.llm_simple, profile, req.text)
    return {"session_id": sid, **result}


# ── SPA static file mount — MUST come after all @app.post / @app.get routes ──
# StaticFiles mounted at "/" intercepts every unmatched path. Any route defined
# after this mount will be shadowed and return 405 for non-GET methods.
_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
