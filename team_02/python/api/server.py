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
from graph import run_agent, run_agent_stream
from inspire import run_inspire_round
from imaging import generate_image, build_room_prompt, build_change_clause, active_provider
from nodes._shared.utils import unwrap_mcp_result, persona_display_label, layout_digits
from nodes.onboarding.persona_compiler import refine_persona
from api import contracts
from api import checkpoints

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


def _write_persona(persona: dict) -> None:
    """Persist the persona to the same file _read_persona loads. Best-effort: used to
    stamp late-arriving fields (e.g. the moodboard) onto an already-compiled persona so
    they survive a restart / returning-user reload."""
    try:
        _PERSONA_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PERSONA_PATH.write_text(
            json.dumps(persona, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


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

class RefinePersonaReq(SessionReq):
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

class ReportReq(SessionReq):
    pass

class CommitReq(SessionReq):
    label: Optional[str] = None

class RestoreReq(SessionReq):
    checkpoint_id: int


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
    # Maintain the checkpoint layer on top of the working draft (graph stays untouched).
    _orig = _original_layout(new_session)
    checkpoints.sync(new_session,
                     json.dumps(_orig) if _orig else "",
                     bool(new_session.get("layout_updated")))
    slot["session"] = new_session
    return {"session_id": sid, **contracts.agent_response_payload(msg, new_session, new_session)}


# ── Streaming turn: per-node progress + token-by-token final answer (SSE) ─────────
# Same agent turn as /api/message, but driven with run_agent_stream so the UI sees
# live progress and the answer streams in. The terminal `result` event carries the
# EXACT payload /api/message returns, so the contract is unchanged. /api/message
# stays as a non-streaming fallback.

_NODE_LABELS: dict[str, str] = {
    "action_classifier": "Reading your request",
    "load_layout":       "Loading the layout",
    "analyze":           "Scoring the rooms",
    "score_interpreter": "Interpreting the scores",
    "detect":            "Detecting conflicts",
    "conflict_reasoner": "Reasoning about conflicts",
    "suggest":           "Generating suggestions",
    "suggestion_critic": "Refining the suggestions",
    "edit_planner":      "Planning the change",
    "apply_edits":       "Applying the change",
    "compare_versions":  "Comparing before and after",
    "evaluator":         "Reviewing the answer",
    "what_next":         "Thinking about next steps",
    "topologic_analysis": "Analysing connectivity",
    "biophilic_audit":   "Auditing greenery",
    "persona_comparison": "Comparing personas",
    "overview_respond":  "Listing the rooms",
    "preview":           "Simulating the change",
    "greet":             "Saying hello",
    "quiz":              "Noting your answer",
    "inspire":           "Dreaming up atmosphere",
    "persona_compiler":  "Building your profile",
}
# Terminal text nodes stream their answer directly (tokens + message_start cover
# them), so we don't also emit a trailing progress label for these.
_TEXT_NODES = {"respond", "detail_respond", "chitchat"}


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/message/stream")
def message_stream(req: MessageReq) -> StreamingResponse:
    """Run one agent turn, streaming progress + the answer as Server-Sent Events.

    Events:
      session       {session_id}
      progress      {node, message}     — a step finished; human label for the UI
      message_start {}                  — begin/replace the streamed answer buffer
      token         {text}              — a chunk of the final answer
      result        <agent_response_payload>  — same shape as /api/message
      error         {message}           — the turn failed; UI shows it, keeps input
    """
    sid, slot = _slot(req.session_id)
    q: "queue.Queue[tuple[str, Any]]" = queue.Queue()

    def worker() -> None:
        try:
            msg, new_session = run_agent_stream(
                req.text, _CTX, slot["session"],
                on_node=lambda name: q.put(("progress", name)),
                on_token=lambda text: q.put(("token", text)),
                on_message_start=lambda: q.put(("message_start", None)),
            )
            # Maintain the checkpoint layer exactly as /api/message does.
            _orig = _original_layout(new_session)
            checkpoints.sync(new_session,
                             json.dumps(_orig) if _orig else "",
                             bool(new_session.get("layout_updated")))
            slot["session"] = new_session
            payload = {"session_id": sid,
                       **contracts.agent_response_payload(msg, new_session, new_session)}
            q.put(("result", payload))
        except Exception as exc:  # a node raised — report, don't hang the client
            import traceback
            traceback.print_exc()
            q.put(("error", str(exc)))

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        yield _sse("session", {"session_id": sid})
        while True:
            kind, payload = q.get()
            if kind == "progress":
                node = payload
                if node in _TEXT_NODES:
                    continue  # the token stream itself is the progress signal
                yield _sse("progress", {"node": node,
                                        "message": _NODE_LABELS.get(node, "Working")})
            elif kind == "message_start":
                yield _sse("message_start", {})
            elif kind == "token":
                yield _sse("token", {"text": payload})
            elif kind == "result":
                yield _sse("result", payload)
                break
            elif kind == "error":
                yield _sse("error", {"message": payload})
                break

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/commit")
def commit_checkpoint(req: CommitReq) -> dict:
    """Commit the working draft as a new checkpoint (cumulative since the last one)."""
    sid, slot = _slot(req.session_id)
    sess = slot["session"]
    cp = checkpoints.commit(sess, req.label)
    if cp is None:
        return {"session_id": sid, "ok": False, "error": "Nothing to commit."}
    return {
        "session_id": sid, "ok": True,
        "checkpoints": checkpoints.summaries(sess),
        "has_uncommitted": checkpoints.has_uncommitted(sess),
        "live_head": checkpoints.live_head(sess),
        "committed_id": cp["id"],
    }


@app.post("/api/checkpoint")
def view_checkpoint(req: RestoreReq) -> dict:
    """Return a checkpoint's scored state for review (non-destructive)."""
    sid, slot = _slot(req.session_id)
    data = checkpoints.view(slot["session"], req.checkpoint_id)
    if data is None:
        return {"session_id": sid, "ok": False, "error": "Checkpoint not found."}
    return {"session_id": sid, "ok": True, **data}


@app.post("/api/restore")
def restore_checkpoint(req: RestoreReq) -> dict:
    """Roll the working draft back to a checkpoint (discards uncommitted edits)."""
    sid, slot = _slot(req.session_id)
    sess = slot["session"]
    cp = checkpoints.restore(sess, req.checkpoint_id)
    if cp is None:
        return {"session_id": sid, "ok": False, "error": "Checkpoint not found."}
    return {
        "session_id": sid, "ok": True,
        "layout_id": sess.get("layout_id"),
        "checkpoints": checkpoints.summaries(sess),
        "has_uncommitted": checkpoints.has_uncommitted(sess),
        "live_head": checkpoints.live_head(sess),
        "restored_label": cp["label"],
        "scores_json": sess.get("last_scores_json", ""),
        "conflicts_json": sess.get("last_conflicts_json", ""),
        "suggestions_json": sess.get("last_suggestions_json", ""),
    }


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

    # Give the curated board an afterlife. Stamp it onto the persona (session + on-disk)
    # so the Report can replay the aesthetic signature even after a server restart or for
    # a returning user — not just within this live session.
    board = all_picks[:6]
    if board:
        prof = new_session.get("persona_profile")
        if isinstance(prof, dict):
            prof["moodboard_urls"] = board
            _write_persona(prof)
        if isinstance(persona, dict):
            persona["moodboard_urls"] = board

    return {
        "session_id":     sid,
        "persona":        persona,
        "moodboard_urls": board,
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
    checkpoints.reset(slot["session"])
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
    checkpoints.reset(slot["session"])

    return {"session_id": sid, "ok": True, "layout_id": layout_id, "name": data.get("name", layout_id)}


# session_id-independent cache: same (provider, layout, room, scores, furniture, persona) → same image
_RENDER_CACHE: dict[str, dict] = {}
# per-key in-flight locks so concurrent callers (eager card render + before/after banner)
# generate ONE image instead of racing to two different ones.
_RENDER_LOCKS: dict[str, threading.Lock] = {}
_RENDER_LOCKS_GUARD = threading.Lock()


def _furn_sig(furniture: list[dict] | None) -> list:
    """A stable signature of a room's furniture (type+material) for the render cache key,
    so changing the island material or adding plants busts the cache."""
    out = []
    for f in furniture or []:
        a = f.get("attributes") or {}
        out.append([a.get("type") or f.get("type") or "", a.get("material") or f.get("material") or ""])
    return sorted(out)


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


def _render_room_image(sess: dict, room: dict, scores: dict, persona: dict,
                       force: bool = False, furniture: list[dict] | None = None) -> tuple[dict, bool]:
    """Canonical per-room render — the single source of truth for a room's image.
    Shared by /api/render-room (card) and /api/compare-initial (before/after 'after')
    so the banner render is byte-identical to the room card. Keyed by
    (provider, layout, room, material, furniture, scores, role). A per-key lock
    de-dupes concurrent callers so they share ONE generated image (not a race to two).
    Returns (out, cached) where out = {image_base64, prompt, provider}. May raise from
    generate_image — callers wrap."""
    provider = active_provider()
    cache_key = hashlib.sha1(json.dumps({
        "provider": provider,
        "layout": sess.get("layout_id", ""),
        "room": room.get("id") or room.get("name"),
        "material": (room.get("attributes", {}) or {}).get("floorMaterial"),
        "furniture": _furn_sig(furniture),
        "scores": scores,
        "role": persona.get("role"),
    }, sort_keys=True).encode()).hexdigest()

    if not force and cache_key in _RENDER_CACHE:
        return _RENDER_CACHE[cache_key], True

    with _RENDER_LOCKS_GUARD:
        lock = _RENDER_LOCKS.setdefault(cache_key, threading.Lock())
    with lock:
        # Re-check inside the lock: a concurrent caller may have just filled the cache.
        if not force and cache_key in _RENDER_CACHE:
            return _RENDER_CACHE[cache_key], True
        prompt = build_room_prompt(room, scores, persona, furniture)
        b64 = generate_image(prompt)
        out = {"image_base64": "data:image/png;base64," + b64, "prompt": prompt, "provider": provider}
        _RENDER_CACHE[cache_key] = out
        return out, False


@app.post("/api/render-room")
def render_room(req: RenderRoomReq) -> dict:
    """Generate a first-person 'how it feels' render of one room, driven by its
    comfort scores + persona. On-demand (FocusCard button); cached per inputs."""
    sid, slot = _slot(req.session_id)
    sess = slot["session"]

    # The Vision renders the COMMITTED state, never the uncommitted working draft.
    raw = checkpoints.vision_layout(sess)
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

    scores = _room_comfort_scores(checkpoints.vision_scores(sess), room)
    persona = sess.get("persona_profile") or {}
    try:
        out, cached = _render_room_image(sess, room, scores, persona, req.force,
                                         furniture=_room_furniture(layout, room))
    except Exception as exc:
        return {"session_id": sid, "ok": False, "error": f"Image generation failed: {exc}"}
    return {"session_id": sid, "ok": True, "cached": cached, **out}


@app.post("/api/report")
def report(req: ReportReq) -> dict:
    """Assemble the Report (Act 3): for every room, its per-sense comfort scores and the
    PROMPT those scores generate (build_room_prompt — NO image generation, so this returns
    in milliseconds). Images are fetched separately, on demand, via /api/render-room. The
    score→prompt→image loop is the report's thesis. `featured` names the 1-3 rooms that
    tell the story (worst overall + the most-recently-edited room) — the client renders
    those eagerly and lazy-renders the rest on expand."""
    sid, slot = _slot(req.session_id)
    sess = slot["session"]

    # Report renders the COMMITTED state (after = latest checkpoint), not the draft.
    raw = checkpoints.vision_layout(sess)
    if not raw:
        return {"session_id": sid, "ok": False, "error": "No layout loaded yet."}
    try:
        layout = json.loads(raw)
    except Exception:
        return {"session_id": sid, "ok": False, "error": "Layout JSON could not be parsed."}

    scores_json = checkpoints.vision_scores(sess)
    if not scores_json:
        return {"session_id": sid, "ok": False, "error": "Run an analysis first."}

    # overallScore keyed by room name, from the cached scores
    overall_by_name: dict[str, float] = {}
    try:
        for r in json.loads(scores_json).get("rooms", []):
            nm = r.get("roomName") or r.get("name")
            if nm is not None and r.get("overallScore") is not None:
                overall_by_name[nm] = float(r["overallScore"])
    except Exception:
        pass

    persona = sess.get("persona_profile") or {}
    out_rooms: list[dict] = []
    for room in layout.get("rooms", []):
        rname = room.get("name")
        scores = _room_comfort_scores(scores_json, room)
        out_rooms.append({
            "room_id": room.get("id"),
            "room_name": rname,
            "room_type": (room.get("attributes", {}) or {}).get("roomType"),
            "comfort_scores": scores,
            "overall_score": overall_by_name.get(rname),
            "prompt": build_room_prompt(room, scores, persona, _room_furniture(layout, room)),
        })

    # featured: worst overall, the biggest-glow-up room (matches the before/after banner
    # so its card render = the banner 'after'), then the most-recently-edited room.
    featured: list[str] = []
    scored = [r for r in out_rooms if r["overall_score"] is not None]
    if scored:
        featured.append(min(scored, key=lambda r: r["overall_score"])["room_name"])
    try:
        sel = _select_compare_room(sess, persona)
        glow = sel["room_after"].get("name") if sel else None
        if glow and glow not in featured and any(r["room_name"] == glow for r in out_rooms):
            featured.append(glow)
    except Exception:
        pass
    edited = (sess.get("layout_diff") or {}).get("room_name")
    if edited and edited not in featured and any(r["room_name"] == edited for r in out_rooms):
        featured.append(edited)

    return {
        "session_id": sid, "ok": True,
        "layout_id": sess.get("layout_id", ""),
        "rooms": out_rooms,
        "featured": featured,
        # The curated aesthetic signature from onboarding's inspire phase — replayed in
        # the Report so the aesthetic the user chose comes back in the output. Sourced
        # from the live session, with the persona.json copy as a returning-user fallback.
        "moodboard_urls": (sess.get("inspire_moodboard_urls")
                           or persona.get("moodboard_urls") or [])[:6],
        # True when the working draft has edits not yet in this (committed) report.
        "has_uncommitted": checkpoints.has_uncommitted(sess),
    }


_SENSES = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]


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


_INITIAL_COMPARE_CACHE: dict[str, dict] = {}


def _original_layout(sess) -> dict | None:
    """The pristine on-disk layout — edits only mutate the session string, never the
    file, so the file IS the 'initial' state for the report's before/after."""
    if _CTX is None:
        return None
    norm = layout_digits(sess.get("layout_id", "") or "")
    try:
        for p in sorted(Path(_CTX.layout_input_dir).glob("*.json")):
            if layout_digits(p.name) == norm:
                return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _furniture_counts(layout: dict) -> dict:
    c: dict = {}
    for f in layout.get("furniture", []):
        rid = (f.get("attributes", {}) or {}).get("roomId")
        c[rid] = c.get(rid, 0) + 1
    return c


def _room_furniture(layout: dict, room: dict) -> list[dict]:
    """The furniture items belonging to one room (by roomId) — for the change clause."""
    rid = room.get("id")
    return [f for f in layout.get("furniture", [])
            if (f.get("attributes", {}) or {}).get("roomId") == rid]


def _room_overall(scores_json: str, room: dict):
    """This room's overallScore (0-1) from a scores JSON, or None."""
    try:
        rid, rname = room.get("id"), room.get("name")
        for r in json.loads(scores_json).get("rooms", []):
            if r.get("roomId") == rid or r.get("roomName") == rname:
                return r.get("overallScore")
    except Exception:
        pass
    return None


def _dwelling_overall(scores_json: str):
    """Whole-home aggregate (0.6·mean + 0.4·worst — mirrors the JS layoutScore)."""
    try:
        ovs = [float(r["overallScore"]) for r in json.loads(scores_json).get("rooms", [])
               if r.get("overallScore") is not None]
        if not ovs:
            return None
        return round(0.6 * (sum(ovs) / len(ovs)) + 0.4 * min(ovs), 4)
    except Exception:
        return None


def _select_compare_room(sess: dict, persona: dict):
    """Pick the report's before/after room: the biggest positive overall gain
    ('biggest glow up'), falling back to the most-changed-by-edits room. Returns a
    dict with the parsed layouts, the chosen room (after/before), the changed keys,
    and both scored states — or None when there's nothing to compare."""
    cur_raw = checkpoints.vision_layout(sess)
    original = _original_layout(sess)
    if not cur_raw or original is None:
        return None
    try:
        current = json.loads(cur_raw)
    except Exception:
        return None
    try:
        after_full = checkpoints.vision_scores(sess) or _score_layout(current, persona)
        before_full = _score_layout(original, persona)
    except Exception:
        return None

    orig_rooms = {r.get("name"): r for r in original.get("rooms", [])}
    fc_cur, fc_orig = _furniture_counts(current), _furniture_counts(original)

    def _changed_keys(rc: dict, ro: dict) -> list[str]:
        ac, ao = rc.get("attributes", {}) or {}, ro.get("attributes", {}) or {}
        ks = [k for k in (set(ac) | set(ao)) if ac.get(k) != ao.get(k)]
        if fc_cur.get(rc.get("id"), 0) != fc_orig.get(ro.get("id"), 0):
            ks.append("furniture")
        return ks

    glow = None          # (room_after, room_before, changed, delta)
    most_changed = None  # (room_after, room_before, changed)
    for rc in current.get("rooms", []):
        ro = orig_rooms.get(rc.get("name"))
        if not ro:
            continue
        changed = _changed_keys(rc, ro)
        if not changed:
            continue
        if most_changed is None or len(changed) > len(most_changed[2]):
            most_changed = (rc, ro, changed)
        oa, ob = _room_overall(after_full, rc), _room_overall(before_full, ro)
        if oa is not None and ob is not None:
            delta = oa - ob
            if delta > 0 and (glow is None or delta > glow[3]):
                glow = (rc, ro, changed, delta)

    if glow is not None:
        room_after, room_before, changed = glow[0], glow[1], glow[2]
    elif most_changed is not None:
        room_after, room_before, changed = most_changed
    else:
        return None

    return {
        "current": current, "original": original,
        "room_after": room_after, "room_before": room_before, "changed": changed,
        "before_full": before_full, "after_full": after_full,
    }


@app.post("/api/compare-initial")
def compare_initial(req: RenderRoomReq) -> dict:
    """Report before/after for the WHOLE editing session: the BIGGEST-GLOW-UP room
    (largest positive overall-score gain) from its INITIAL (on-disk) state → its FINAL
    (current) state, with per-sense deltas and both prompts. The 'after' is the canonical
    room render (shared cache with the report card = single source of truth); the 'before'
    is generated anchored on that after image PLUS an explicit change clause, so the scene
    stays consistent while the mood genuinely shifts."""
    sid, slot = _slot(req.session_id)
    sess = slot["session"]
    persona = sess.get("persona_profile") or {}

    sel = _select_compare_room(sess, persona)
    if sel is None:
        return {"session_id": sid, "ok": False, "error": "no edits to compare"}
    current, original = sel["current"], sel["original"]
    room_after, room_before, changed = sel["room_after"], sel["room_before"], sel["changed"]
    after_full, before_full = sel["after_full"], sel["before_full"]
    fc_cur, fc_orig = _furniture_counts(current), _furniture_counts(original)

    cache_key = hashlib.sha1(json.dumps({
        "p": active_provider(), "l": sess.get("layout_id", ""),
        "r": room_after.get("id") or room_after.get("name"),
        "a": room_after.get("attributes"), "b": room_before.get("attributes"),
        "fc": [fc_cur.get(room_after.get("id"), 0), fc_orig.get(room_before.get("id"), 0)],
    }, sort_keys=True).encode()).hexdigest()
    if not req.force and cache_key in _INITIAL_COMPARE_CACHE:
        return {"session_id": sid, "ok": True, "cached": True, **_INITIAL_COMPARE_CACHE[cache_key]}

    after_scores = _room_comfort_scores(after_full, room_after)
    before_scores = _room_comfort_scores(before_full, room_before)
    furn_after = _room_furniture(current, room_after)
    furn_before = _room_furniture(original, room_before)

    try:
        # AFTER = the canonical room render (same cache the report card uses → identical image).
        after_out, _ = _render_room_image(sess, room_after, after_scores, persona, req.force,
                                          furniture=furn_after)
        after_image = after_out["image_base64"]
        after_prompt = after_out["prompt"]
        after_raw = after_image.split(",", 1)[-1]  # strip data: prefix for the anchor

        # BEFORE = anchored on the after image + an IMPERATIVE edit clause, so the scene
        # holds (same room/camera/composition) but every change reads distinctly different.
        # Display prompt is the clean before-state scene; the clause is generation-only.
        before_prompt = build_room_prompt(room_before, before_scores, persona, furn_before)
        clause = build_change_clause(
            room_before, room_after, before_scores, after_scores, furn_before, furn_after,
        )
        gen_prompt = before_prompt + (" " + clause if clause else "")
        before_b64 = generate_image(gen_prompt, reference_b64=after_raw)
    except Exception as exc:
        return {"session_id": sid, "ok": False, "error": f"Image generation failed: {exc}"}

    deltas = {s: {"before": before_scores.get(s), "after": after_scores.get(s)}
              for s in _SENSES if (s in before_scores or s in after_scores)}
    out = {
        "before_image": "data:image/png;base64," + before_b64,
        "after_image": after_image,
        "deltas": deltas, "room": room_after.get("name"), "changed": changed,
        # the two prompts so the slider can show how the score→prompt drove the render
        "before_prompt": before_prompt,
        "after_prompt": after_prompt,
        # overall scores so the slider can show initial→now numbers, not just images
        "room_before_overall": _room_overall(before_full, room_before),
        "room_after_overall": _room_overall(after_full, room_after),
        "dwelling_before": _dwelling_overall(before_full),
        "dwelling_after": _dwelling_overall(after_full),
        "provider": active_provider(),
    }
    _INITIAL_COMPARE_CACHE[cache_key] = out
    return {"session_id": sid, "ok": True, "cached": False, **out}


@app.post("/api/refine-persona")
def refine_persona_endpoint(req: RefinePersonaReq) -> dict:
    """Refine the saved persona from a free-text statement ("I got a dog, and noise
    bothers me more"). Patches the persona, persists it to disk, and updates the
    session — so the change flows into scoring and every response via the persona
    context. Returns the updated persona + a short confirmation."""
    sid, slot = _slot(req.session_id)
    current = slot["session"].get("persona_profile") or _read_persona() or {}
    updated, message = refine_persona(_CTX.llm_smart, current, req.text, str(_PERSONA_PATH))
    slot["session"]["persona_profile"] = updated
    return {"session_id": sid, "ok": True, "persona": updated, "message": message}


# ── SPA static file mount — MUST come after all @app.post / @app.get routes ──
# StaticFiles mounted at "/" intercepts every unmatched path. Any route defined
# after this mount will be shadowed and return 405 for non-GET methods.
_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
