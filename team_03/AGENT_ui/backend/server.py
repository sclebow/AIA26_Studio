"""
FastAPI server — entry point for the AGENT_ui backend.
Run with:  python server.py
or:        uvicorn server:app --port 3000 --reload
"""
from __future__ import annotations

import asyncio
import json
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
import isovist
import spatial_assistant
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


def _live_layout_json() -> str:
    """The layout Grasshopper currently shows = the live workspace layout
    (team_03/workspace/session_active.json), which already includes the agent's
    placements. Used as set_observer's `layout_json` so the isovist runs on the
    real floor + obstacles. Falls back to the in-memory session layout."""
    try:
        f = Path(__file__).resolve().parents[2] / "workspace" / "session_active.json"
        if f.exists():
            return f.read_text(encoding="utf-8")
    except Exception:
        pass
    st = session.get_session() or {}
    return json.dumps(st["layout"]) if st.get("layout") else ""


# Small rolling chat history for the spatial assistant (so follow-ups like
# "now check collisions" keep context). Capped; the system prompt always carries
# the current layout + observer so mild staleness is harmless.
_spatial_history: "list[dict]" = []


async def _handle_spatial(content: str, websocket: WebSocket) -> None:
    """Answer an observer/visibility/path question with the Rhino-free spatial
    assistant: it runs deterministic analysis, draws the result in the viewport,
    and replies in chat."""
    layout_json = _live_layout_json()
    if not layout_json:
        await manager.send_personal(websocket, {
            "type": MessageType.agent_response.value,
            "content": "Load a layout first, then ask me about visibility, a person, or a path.",
        })
        return
    try:
        layout = json.loads(layout_json)
    except Exception:
        await manager.send_personal(websocket, {
            "type": MessageType.agent_response.value,
            "content": "I couldn't read the current layout. Try reloading it.",
        })
        return

    # The spatial assistant uses the Anthropic SDK directly, so it always runs on
    # Anthropic (its own key/model) even when the main pipeline is on Google.
    from pipeline_bridge import anthropic_aux_config
    aux_key, aux_model = anthropic_aux_config()

    async def emit(msg: dict) -> None:
        await manager.send_personal(websocket, msg)

    try:
        answer = await spatial_assistant.handle(
            content, list(_spatial_history), layout, session.get_observer(),
            emit, session.set_observer, aux_key, aux_model,
        )
    except Exception as exc:
        answer = f"Spatial analysis error: {exc}"

    _spatial_history.append({"role": "user", "content": content})
    _spatial_history.append({"role": "assistant", "content": answer})
    del _spatial_history[:-6]  # keep the last 3 exchanges

    await manager.send_personal(websocket, {
        "type": MessageType.agent_response.value, "content": answer,
    })


def _isovist_for_point(layout_json: str, point_str) -> "list | None":
    """Compute the visibility polygon for a PERSON observer at point_str ('x,y,h')."""
    try:
        layout = json.loads(layout_json) if layout_json else None
        if not layout or not point_str:
            return None
        parts = [float(p) for p in str(point_str).split(",") if p.strip() != ""]
        if len(parts) < 2:
            return None
        x, y = parts[0], parts[1]
        h = parts[2] if len(parts) > 2 else 1.7
        return isovist.compute(layout, x, y, h)
    except Exception as exc:
        print(f"[isovist] person compute failed: {exc}")
        return None


def _isovist_for_path(layout_json: str, path_str, height) -> "list | None":
    """Compute the union isovist along a PATH ('x1,y1;x2,y2;...')."""
    try:
        layout = json.loads(layout_json) if layout_json else None
        if not layout or not path_str:
            return None
        pts = []
        for chunk in str(path_str).split(";"):
            c = [v for v in chunk.split(",") if v.strip() != ""]
            if len(c) >= 2:
                pts.append((float(c[0]), float(c[1])))
        if not pts:
            return None
        try:
            h = float(height)
        except (TypeError, ValueError):
            h = 1.7
        return isovist.compute_path(layout, pts, h)
    except Exception as exc:
        print(f"[isovist] path compute failed: {exc}")
        return None

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
                    # A pipeline run is paused at its checkpoint. A STRONG observer
                    # intent ("move the person", "place an observer") means the user
                    # switched to spatial work → abort the stale run and handle it,
                    # so the pipeline can't keep eating every message. Weak wording
                    # (path/view) stays a checkpoint decision so we don't hijack a
                    # real placement run.
                    if spatial_assistant.is_strong_spatial_query(content):
                        agent_runner.abort_session(websocket)
                        await _handle_spatial(content, websocket)
                    else:
                        agent_runner.submit_decision(content)
                elif spatial_assistant.is_spatial_query(content):
                    # Observer / visibility / path question → lightweight assistant
                    # (pure Python, no Rhino). Draws into the viewport + answers.
                    await _handle_spatial(content, websocket)
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
                data["layout_json"] = _live_layout_json()
                is_live = bool(data.get("live"))  # True while the person is being dragged

                if is_live:
                    # Fast path: Python isovist only — no MCP/Grasshopper push.
                    # Skipping GH keeps drag updates at ~5ms instead of >100ms.
                    iso = _isovist_for_point(data["layout_json"], data.get("point_str"))
                    if iso:
                        session.set_observer({
                            "mode": "person",
                            "point_str": data.get("point_str"),
                            "height": data.get("height", 1.7),
                            "isovist": iso,
                        })
                        await manager.send_personal(websocket, {
                            "type": "observer_result",
                            "mode": "person",
                            "status": "ok",
                            "isovist": iso,
                        })
                else:
                    # Full path: MCP push to Grasshopper + Python isovist.
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
                    iso = _isovist_for_point(data["layout_json"], data.get("point_str"))
                    session.set_observer({
                        "mode": "person",
                        "point_str": data.get("point_str"),
                        "height": data.get("height", 1.7),
                        "isovist": iso,
                    })
                    await manager.send_personal(websocket, {
                        "type": "observer_result",
                        "mode": "person",
                        "status": result.get("status"),
                        "isovist": iso,
                    })

            elif msg_type == "observer_path":
                # Unified set_observer tool, PATH mode. Use the live workspace layout.
                data["layout_json"] = _live_layout_json()
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
                iso = _isovist_for_path(data["layout_json"], data.get("path_str"), data.get("height"))
                session.set_observer({
                    "mode": "path",
                    "path_str": data.get("path_str"),
                    "height": data.get("height", 1.7),
                    "isovist": iso,
                })
                await manager.send_personal(websocket, {
                    "type": "observer_result",
                    "mode": "path",
                    "status": result.get("status"),
                    "isovist": iso,
                })

            elif msg_type == "provider_switch":
                # Switch the active PIPELINE provider + model (anthropic/google).
                # Applies to the next chat session (build_context). Auxiliary features
                # (pure_chat, spatial_assistant) always stay on Anthropic. If the chosen
                # provider's API key is missing, the active provider is left unchanged
                # and an error ack tells the user which key to add and where.
                from pipeline_bridge import set_pipeline_llm
                provider = str(data.get("provider", "anthropic"))
                model_key = data.get("model")
                model_key = str(model_key) if model_key is not None else None
                try:
                    active_provider, full_model = set_pipeline_llm(provider, model_key)
                    await manager.send_personal(websocket, {
                        "type": "provider_switch_ack",
                        "provider": active_provider,
                        "model": model_key,
                        "full_model": full_model,
                        "status": "ok",
                    })
                except ValueError as exc:
                    # _required_env raises "Missing or empty required environment variable: GOOGLE_API_KEY"
                    detail = str(exc)
                    missing_key = None
                    if "required environment variable:" in detail:
                        missing_key = detail.split(":", 1)[1].strip()
                    from pipeline_bridge import _team_dir
                    env_path = str(_team_dir().parent / ".env")
                    await manager.send_personal(websocket, {
                        "type": "provider_switch_ack",
                        "provider": provider,
                        "status": "error",
                        "missingKey": missing_key,
                        "envPath": env_path,
                        "detail": (
                            f"Cannot switch to {provider}: {detail}. "
                            f"Add {missing_key or 'the API key'} to {env_path} and restart the backend."
                        ),
                    })

            elif msg_type == "pure_chat":
                # Pure chatbot — direct Anthropic call, no pipeline, no LangGraph.
                content = str(data.get("content", "")).strip()
                history = data.get("history", [])  # [{role, content}, ...]
                if not content:
                    continue
                try:
                    import anthropic
                    from pipeline_bridge import anthropic_aux_config

                    # Direct Anthropic chatbot — always runs on Anthropic's own
                    # key/model, independent of the main pipeline's provider.
                    aux_key, model = anthropic_aux_config()

                    client = anthropic.AsyncAnthropic(api_key=aux_key)

                    # Build messages: history + new user message
                    messages = [
                        {"role": m["role"], "content": m["content"]}
                        for m in history
                        if m.get("role") in ("user", "assistant") and m.get("content")
                    ]
                    messages.append({"role": "user", "content": content})

                    response = await client.messages.create(
                        model=model,
                        max_tokens=1024,
                        system=(
                            "You are a helpful architectural design assistant specializing in "
                            "spatial analysis, accessibility, layout planning, and architectural "
                            "concepts. Answer clearly and concisely. You are NOT running any "
                            "tools or workflow — this is a direct conversation."
                        ),
                        messages=messages,
                    )
                    reply = "".join(
                        block.text for block in response.content
                        if getattr(block, "type", None) == "text"
                    )
                    await manager.send_personal(websocket, {
                        "type": "pure_chat_response",
                        "content": reply,
                        "model": model,
                    })
                except Exception as exc:
                    await manager.send_personal(websocket, {
                        "type": "pure_chat_response",
                        "content": f"Error: {exc}",
                        "model": "",
                    })

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
