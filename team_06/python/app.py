from __future__ import annotations

import json
import threading
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from _runtime.bootstrap import bootstrap
from graph import run_agent


def _safe_json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _format_programs(programs: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for program in programs:
        if not isinstance(program, str) or not program.strip():
            continue
        normalized = program.strip()
        counts[normalized] = counts.get(normalized, 0) + 1

    return [
        {
            "name": program,
            "count": count,
            "label": f"{count} x {program}" if count > 1 else program,
        }
        for program, count in counts.items()
    ]


def _format_pairs(pairs: Any) -> list[str]:
    if not isinstance(pairs, list):
        return []

    formatted: list[str] = []
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        left, right = pair
        if isinstance(left, str) and left.strip() and isinstance(right, str) and right.strip():
            formatted.append(f"{left.strip()} - {right.strip()}")
    return formatted


def _build_brief(topology_graph_json_string: str | None) -> dict[str, Any] | None:
    payload = _safe_json_loads(topology_graph_json_string)
    graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
    description = payload.get("description") if isinstance(payload.get("description"), str) else ""

    programs = graph.get("programs") if isinstance(graph.get("programs"), list) else []
    brief = {
        "rooms": _format_programs(programs),
        "access": _format_pairs(graph.get("access_pairs")),
        "adjacency": _format_pairs(graph.get("adjacency_pairs")),
        "separation": _format_pairs(graph.get("not_adjacency_pairs")),
        "description": description.strip(),
        "summary": description.strip() or (", ".join(programs) if programs else ""),
    }

    has_content = any(
        [brief["rooms"], brief["access"], brief["adjacency"], brief["separation"], brief["description"]]
    )
    return brief if has_content else None


def _parse_layout(raw_layout: str | None) -> dict[str, Any] | None:
    payload = _safe_json_loads(raw_layout)
    return payload or None


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class LayoutRequest(BaseModel):
    session_id: str
    layout_json: str | None = None


class SessionRequest(BaseModel):
    session_id: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    app.state.ctx = bootstrap()
    app.state.sessions = {}
    app.state.chat_runs = {}
    try:
        yield
    finally:
        app.state.ctx.mcp_client.close()


app = FastAPI(title="inHabit Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _session_store() -> dict[str, dict[str, Any]]:
    return app.state.sessions


def _chat_run_store() -> dict[str, dict[str, Any]]:
    return app.state.chat_runs


def _get_or_create_session(session_id: str | None) -> tuple[str, dict[str, Any]]:
    sid = session_id or str(uuid4())
    sessions = _session_store()
    session = sessions.setdefault(sid, {"feedback_history": []})
    session.setdefault("feedback_history", [])
    return sid, session


def _build_chat_payload(session_id: str, response: str, updated_session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "message": response,
        "brief": _build_brief(updated_session.get("topology_graph_json_string")),
        "layout": _parse_layout(updated_session.get("layout_json_string")),
        "needs_user_input": updated_session.get("needs_user_input", False),
        "status_messages": updated_session.get("status_messages", []),
    }


def _run_chat_in_background(session_id: str, message: str) -> None:
    run_state = _chat_run_store()[session_id]

    def on_status(messages: list[str]) -> None:
        run_state["status"] = "running"
        run_state["status_messages"] = list(messages)

    try:
        _, session = _get_or_create_session(session_id)
        response, updated_session = run_agent(message, app.state.ctx, session, status_callback=on_status)
        _session_store()[session_id] = updated_session
        run_state["status"] = "completed"
        run_state["status_messages"] = updated_session.get("status_messages", [])
        run_state["result"] = _build_chat_payload(session_id, response, updated_session)
        run_state["error"] = None
    except Exception as exc:
        run_state["status"] = "failed"
        run_state["error"] = str(exc)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/chat")
def chat(body: ChatRequest) -> dict[str, Any]:
    sid, session = _get_or_create_session(body.session_id)
    response, updated_session = run_agent(body.message, app.state.ctx, session)
    _session_store()[sid] = updated_session

    return _build_chat_payload(sid, response, updated_session)


@app.post("/chat/start")
def start_chat(body: ChatRequest) -> dict[str, Any]:
    sid, _ = _get_or_create_session(body.session_id)
    existing_run = _chat_run_store().get(sid)
    if existing_run and existing_run.get("status") == "running":
        return {
            "session_id": sid,
            "status": "running",
            "status_messages": existing_run.get("status_messages", []),
        }

    _chat_run_store()[sid] = {
        "status": "running",
        "status_messages": [],
        "result": None,
        "error": None,
    }
    worker = threading.Thread(target=_run_chat_in_background, args=(sid, body.message), daemon=True)
    worker.start()
    return {"session_id": sid, "status": "running", "status_messages": []}


@app.get("/chat/status/{session_id}")
def get_chat_status(session_id: str) -> dict[str, Any]:
    run_state = _chat_run_store().get(session_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail="No active chat run for this session")

    payload = {
        "session_id": session_id,
        "status": run_state.get("status", "running"),
        "status_messages": run_state.get("status_messages", []),
    }
    if run_state.get("status") == "completed":
        payload["result"] = run_state.get("result")
    if run_state.get("status") == "failed":
        payload["error"] = run_state.get("error") or "Chat run failed"
    return payload


@app.post("/upload-layout")
async def upload_layout(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        session_id = form.get("session_id")
        file = form.get("file")
        if file is None:
            raise HTTPException(status_code=400, detail="Missing layout file")
        raw_bytes = await file.read()
        try:
            layout_payload = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid layout JSON: {exc}") from exc
        layout_json = json.dumps(layout_payload)
    else:
        body = LayoutRequest.model_validate(await request.json())
        session_id = body.session_id
        layout_json = body.layout_json

    sid, session = _get_or_create_session(session_id)

    session["input_layout_json_string"] = layout_json
    _session_store()[sid] = session

    layout = _parse_layout(layout_json)
    return {
        "ok": True,
        "session_id": sid,
        "layoutId": (layout or {}).get("layoutId", "uploaded") if layout_json else None,
    }


@app.post("/restore-layout")
def restore_layout(body: LayoutRequest) -> dict[str, Any]:
    sid, session = _get_or_create_session(body.session_id)
    session["layout_json_string"] = body.layout_json
    _session_store()[sid] = session
    return {"ok": True, "session_id": sid}


@app.delete("/session")
def clear_session(body: SessionRequest) -> dict[str, bool]:
    _session_store().pop(body.session_id, None)
    _chat_run_store().pop(body.session_id, None)
    return {"ok": True}