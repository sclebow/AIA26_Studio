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

import hashlib

from _runtime.bootstrap import bootstrap
from graph import run_agent
from inspire import run_inspire_round, profile_chat_reply
from imaging import generate_image, build_room_prompt, active_provider
from nodes._shared.utils import unwrap_mcp_result, persona_display_label
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

class RenderRoomReq(SessionReq):
    room_id: Optional[str] = None
    room_name: Optional[str] = None
    force: bool = False


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


# session_id-independent cache: same (provider, layout, room, scores, persona) → same image
_RENDER_CACHE: dict[str, dict] = {}


def _room_comfort_scores(scores_json: str, room: dict) -> dict[str, float]:
    """Pull this room's per-sense comfort scores (0-1) from the cached scores JSON."""
    try:
        data = json.loads(scores_json)
    except Exception:
        return {}
    rid, rname = room.get("id"), room.get("name")
    for r in data.get("rooms", []):
        if r.get("roomId") == rid or r.get("id") == rid or r.get("roomName") == rname:
            return {k: float(v) for k, v in (r.get("comfortScores") or {}).items()}
    return {}


@app.post("/api/render-room")
def render_room(req: RenderRoomReq) -> dict:
    """Generate a first-person 'how it feels' render of one room, driven by its
    comfort scores + persona. On-demand (FocusCard button); cached per inputs."""
    sid, slot = _slot(req.session_id)
    sess = slot["session"]

    raw = sess.get("layout_json_string", "")
    if not raw:
        return {"session_id": sid, "ok": False, "error": "No layout loaded yet."}
    try:
        layout = json.loads(raw)
    except Exception:
        return {"session_id": sid, "ok": False, "error": "Layout JSON could not be parsed."}

    rooms = layout.get("rooms", [])
    room = next(
        (r for r in rooms if (req.room_id and r.get("id") == req.room_id)
         or (req.room_name and r.get("name") == req.room_name)),
        None,
    )
    if not room:
        return {"session_id": sid, "ok": False, "error": "Room not found in current layout."}

    scores = _room_comfort_scores(sess.get("last_scores_json", ""), room)
    persona = sess.get("persona_profile") or {}
    provider = active_provider()

    cache_key = hashlib.sha1(json.dumps({
        "provider": provider,
        "layout": sess.get("layout_id", ""),
        "room": room.get("id") or room.get("name"),
        "material": (room.get("attributes", {}) or {}).get("floorMaterial"),
        "scores": scores,
        "role": persona.get("role"),
    }, sort_keys=True).encode()).hexdigest()

    if not req.force and cache_key in _RENDER_CACHE:
        return {"session_id": sid, "ok": True, "cached": True, **_RENDER_CACHE[cache_key]}

    prompt = build_room_prompt(room, scores, persona)
    try:
        b64 = generate_image(prompt)
    except Exception as exc:
        return {"session_id": sid, "ok": False, "error": f"Image generation failed: {exc}"}

    out = {"image_base64": "data:image/png;base64," + b64, "prompt": prompt, "provider": provider}
    _RENDER_CACHE[cache_key] = out
    return {"session_id": sid, "ok": True, "cached": False, **out}


_SENSES = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]
_COMPARE_CACHE: dict[str, dict] = {}


def _score_layout(layout_dict: dict, persona: dict) -> str:
    """Score a layout via the in-process comfort tool (same call the agent uses)."""
    persona_label = persona_display_label(persona)
    weights = persona.get("comfort_weights")
    pers = persona.get("personality", 0)
    if isinstance(pers, str):
        pers = {"introvert": -1.0, "extrovert": 1.0}.get(pers.strip().lower(), 0.0)
    try:
        personality = float(pers or 0)
    except (TypeError, ValueError):
        personality = 0.0
    args = {"layout_json": json.dumps(layout_dict), "persona": persona_label,
            "room_ids": "all", "personality": personality}
    if weights:
        args["weights_override"] = json.dumps(weights)
    return unwrap_mcp_result(_CTX.mcp_client.call_tool("compute_comfort_scores", args))


@app.post("/api/compare-room")
def compare_room(req: RenderRoomReq) -> dict:
    """Before/after for the most recent edit of a room: revert the edit on a clone,
    re-score it, generate both renders (after, then before anchored on after), and
    return per-sense deltas. Powers the FocusCard before/after slider (Phase 2)."""
    sid, slot = _slot(req.session_id)
    sess = slot["session"]
    diff = sess.get("layout_diff") or {}
    if not diff or not diff.get("attribute"):
        return {"session_id": sid, "ok": False, "error": "No recent edit to compare."}

    raw = sess.get("layout_json_string", "")
    try:
        layout_after = json.loads(raw)
    except Exception:
        return {"session_id": sid, "ok": False, "error": "Layout JSON could not be parsed."}

    rid, rname = diff.get("room_id"), diff.get("room_name")
    rooms = layout_after.get("rooms", [])
    room_after = next((r for r in rooms if r.get("id") == rid or r.get("name") == rname), None)
    if not room_after:
        return {"session_id": sid, "ok": False, "error": "Edited room not found."}

    persona = sess.get("persona_profile") or {}
    provider = active_provider()
    attr, old, new = diff["attribute"], diff.get("old_value"), diff.get("new_value")

    cache_key = hashlib.sha1(json.dumps({
        "p": provider, "l": sess.get("layout_id", ""), "r": rid or rname,
        "a": attr, "o": old, "n": new,
    }, sort_keys=True).encode()).hexdigest()
    if not req.force and cache_key in _COMPARE_CACHE:
        return {"session_id": sid, "ok": True, "cached": True, **_COMPARE_CACHE[cache_key]}

    after_scores = _room_comfort_scores(sess.get("last_scores_json", ""), room_after)

    # BEFORE: clone, revert the changed attribute, re-score.
    layout_before = json.loads(raw)
    room_before = next((r for r in layout_before.get("rooms", [])
                        if r.get("id") == rid or r.get("name") == rname), None)
    room_before.setdefault("attributes", {})[attr] = old
    try:
        before_scores = _room_comfort_scores(_score_layout(layout_before, persona), room_before)
    except Exception as exc:
        return {"session_id": sid, "ok": False, "error": f"Re-scoring failed: {exc}"}

    try:
        after_b64 = generate_image(build_room_prompt(room_after, after_scores, persona))
        before_b64 = generate_image(build_room_prompt(room_before, before_scores, persona),
                                    reference_b64=after_b64)
    except Exception as exc:
        return {"session_id": sid, "ok": False, "error": f"Image generation failed: {exc}"}

    deltas = {s: {"before": before_scores.get(s), "after": after_scores.get(s)}
              for s in _SENSES if (s in before_scores or s in after_scores)}

    out = {
        "before_image": "data:image/png;base64," + before_b64,
        "after_image": "data:image/png;base64," + after_b64,
        "deltas": deltas, "attribute": attr, "old_value": old, "new_value": new,
        "room": rname, "provider": provider,
    }
    _COMPARE_CACHE[cache_key] = out
    return {"session_id": sid, "ok": True, "cached": False, **out}


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
