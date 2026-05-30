"""
Real LangGraph pipeline runner for the AGENT_ui backend.

Runs the EXACT pipeline from team_03/python/ (graph.build_graph + app.invoke) in
a worker thread, bridging the checkpoint's blocking `input("Your decision: ")` to
WebSocket decisions and turning the checkpoint's printed menu into a structured
payload for the UI.

A single chat session = one app.invoke() call (the graph loops at user_checkpoint
until the user approves/ends). The first chat_message starts the session; further
chat_message / chat_decision values are fed into the checkpoint's input queue.
"""
from __future__ import annotations

import asyncio
import builtins
import contextlib
import queue
import threading
from typing import Any, Dict, Optional

from websocket_manager import ConnectionManager, MessageType
from pipeline_bridge import (
    build_context,
    StdoutTee,
    CheckpointParser,
    read_session_layout,
)


# Graph node names → ProcessPanel card names (where they differ).
_NODE_ALIAS = {
    "path": "path_analysis",
    "user_checkpoint": "checkpoint",
}


# Sentinel pushed into the input queue to abort a blocked checkpoint so the
# worker thread can unwind cleanly (e.g. when its client disconnects/refreshes).
_ABORT = "\x00__ABORT__\x00"


class _Aborted(Exception):
    pass


class _Session:
    def __init__(self) -> None:
        self.thread: Optional[threading.Thread] = None
        self.input_queue: "queue.Queue[str]" = queue.Queue()
        self.active: bool = False
        self.owner: Any = None   # the websocket that started this session


# Single active session (local single-user backend).
_session = _Session()
_session_lock = threading.Lock()


def is_active() -> bool:
    return _session.active


def owns_active(websocket: Any) -> bool:
    return _session.active and _session.owner is websocket


def submit_decision(value: str) -> None:
    """Feed a decision (chip token or free text) to the blocked checkpoint input()."""
    if _session.active:
        _session.input_queue.put(value)


def abort_session(websocket: Any = None) -> None:
    """Abort the active session (e.g. on client disconnect). If `websocket` is
    given, only abort when it owns the session. Unblocks the checkpoint input()
    and frees the slot so a fresh session can start."""
    with _session_lock:
        if not _session.active:
            return
        if websocket is not None and _session.owner is not websocket:
            return
        _session.active = False
        _session.owner = None
        _session.input_queue.put(_ABORT)


async def start_session(
    prompt: str,
    layout_name: Optional[str],
    manager: ConnectionManager,
    websocket: Any,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Start a real pipeline run in a worker thread. Returns immediately; all
    further communication happens over WebSocket via the thread's callbacks."""
    with _session_lock:
        if _session.active:
            if _session.owner is websocket:
                # Same client, run in progress → treat as a checkpoint decision.
                _session.input_queue.put(prompt)
                return
            # A different/stale client owns the slot → abort it and take over.
            _session.input_queue.put(_ABORT)
        _session.active = True
        _session.owner = websocket
        _session.input_queue = queue.Queue()

    def emit(msg: Dict[str, Any]) -> None:
        """Send a WS message from the worker thread to the main event loop."""
        try:
            asyncio.run_coroutine_threadsafe(manager.send_personal(websocket, msg), loop)
        except Exception:
            pass

    def emit_event(node: str, status: str, data: Any = None) -> None:
        """Emit a per-node pipeline event (drives the Pipeline panel + Log)."""
        ui_node = _NODE_ALIAS.get(node, node)
        msg = {"type": MessageType.agent_event.value, "node": ui_node, "status": status}
        if data is not None:
            msg["data"] = data
        emit(msg)

    # Tracks whether this turn produced any score, so a conversational reply that
    # never ran the analysis tools can be backfilled deterministically (below).
    scores_emitted = {"v": False}

    def emit_scores(overall: Any, grade: Any, breakdown: Dict[str, Any]) -> None:
        """Map a score + per-tool breakdown → the Dashboard ScoreData shape and
        push it as a state_update so the Analysis Dashboard reflects the score.
        Works from the scoring node (placement runs) AND from the parsed checkpoint
        breakdown (analysis/query runs where the scoring node never executes)."""
        breakdown = breakdown or {}
        if not breakdown and not overall:
            return
        scores_emitted["v"] = True

        def _sc(tool: str) -> float:
            return round(float((breakdown.get(tool) or {}).get("score", 0) or 0))

        def _wt(tool: str) -> float:
            return float((breakdown.get(tool) or {}).get("weight", 0) or 0)

        scores = {
            "overall": round(float(overall or 0)),
            "grade": grade or "?",
            "collision": _sc("collision"),
            "visibility": _sc("visibility"),
            "path": _sc("path"),
            "reachability": _sc("reachability"),
            "orientation": _sc("orientation"),
            "weights": {
                "collision": _wt("collision"),
                "visibility": _wt("visibility"),
                "path": _wt("path"),
                "reachability": _wt("reachability"),
                "orientation": _wt("orientation"),
            },
        }
        emit({"type": MessageType.state_update.value, "field": "scores", "data": scores})

    def run() -> None:
        parser = CheckpointParser()
        ctx = None
        state = {"current_node": None}

        def on_line(line: str) -> None:
            parser.feed(line)

        # Patched input(): the call itself signals "menu printed, awaiting decision".
        def patched_input(prompt_text: str = "") -> str:
            payload = parser.take_checkpoint()
            emit(payload)
            # Reflect the checkpoint score in the Analysis Dashboard (the scoring
            # node doesn't run on analysis/query paths, so use the parsed breakdown).
            if payload.get("breakdown") or payload.get("score") is not None:
                emit_scores(payload.get("score"), payload.get("grade"), payload.get("breakdown") or {})
            if ctx is not None:
                layout = read_session_layout(ctx.workspace_path)
                if layout:
                    emit({
                        "type": MessageType.state_update.value,
                        "field": "layout",
                        "data": layout,
                        "proposal": False,
                    })
            token = _session.input_queue.get()
            if token == _ABORT:
                raise _Aborted()
            return token

        import sys
        tee = StdoutTee(sys.stdout, on_line)
        real_input = builtins.input

        async def consume(app: Any, initial_state: Dict[str, Any]) -> Dict[str, Any]:
            """Stream node-level events from the real graph for live progress."""
            final_state: Dict[str, Any] = {}
            async for ev in app.astream_events(initial_state, version="v2"):
                etype = ev.get("event")
                node = (ev.get("metadata") or {}).get("langgraph_node")
                name = ev.get("name")
                # Only react to the node-level runnable (name == node), not its
                # child runnables (LLM calls, sub-chains) which share langgraph_node.
                is_node_level = bool(node) and name == node
                if is_node_level and etype == "on_chain_start":
                    state["current_node"] = node
                    emit_event(node, "started")
                elif is_node_level and etype == "on_chain_end":
                    emit_event(node, "completed")
                    # Capture the latest full state when the graph finishes.
                    out = (ev.get("data") or {}).get("output")
                    if isinstance(out, dict):
                        final_state.update(out)
                        # When scoring finishes, push the breakdown to the Dashboard.
                        sr = out.get("scoring_results")
                        if isinstance(sr, dict):
                            emit_scores(sr.get("total_score"), sr.get("grade"), sr.get("breakdown") or {})
                elif etype == "on_chain_error" and node:
                    emit_event(node, "error", str((ev.get("data") or {}).get("error", "")))
            return final_state

        agent_loop = asyncio.new_event_loop()
        try:
            # Immediate feedback + setup progress (visible in the Log).
            emit_event("setup", "started")
            ctx = build_context(
                layout_name or "",
                progress=lambda m: emit_event("setup", "completed", m),
            )
            from graph import build_graph, _build_initial_state

            app = build_graph(ctx)
            initial_state = _build_initial_state(prompt, ctx)

            builtins.input = patched_input
            asyncio.set_event_loop(agent_loop)
            with contextlib.redirect_stdout(tee):
                final_state = agent_loop.run_until_complete(consume(app, initial_state))

            final_response = (final_state or {}).get("final_response") or "Session complete."
            emit({"type": MessageType.agent_response.value, "content": str(final_response)})

            layout = read_session_layout(ctx.workspace_path)
            if layout:
                emit({
                    "type": MessageType.state_update.value,
                    "field": "layout",
                    "data": layout,
                    "proposal": False,
                })

            # Backfill: if the turn answered conversationally without running the
            # analysis tools (no score emitted), compute the score deterministically
            # so "Analyse the layout" still populates the Analysis Dashboard.
            if not scores_emitted["v"]:
                try:
                    from adapters.analysis_adapter import run_all
                    target = layout or (ctx.layout_data if ctx else None)
                    if target:
                        res = run_all(
                            target,
                            profile_config=(final_state or {}).get("profile_config"),
                            space_config=(final_state or {}).get("space_config"),
                        )
                        sr = res.get("scoring_results") or {}
                        emit_scores(sr.get("total_score"), sr.get("grade"), sr.get("breakdown") or {})
                except Exception as exc:
                    print(f"[analyze] deterministic backfill failed: {exc}")
        except _Aborted:
            # Client disconnected / superseded — unwind quietly, no chat error.
            pass
        except Exception as exc:  # noqa: BLE001 — surface any failure in chat + panel
            cur = state.get("current_node")
            if cur:
                emit_event(cur, "error", str(exc))
            emit({
                "type": MessageType.agent_response.value,
                "content": (
                    f"**Pipeline error"
                    + (f" at `{cur}`" if cur else "")
                    + f":** {exc}\n\n"
                    "Check that Rhino + Swiftlet (MCP on :3002) are running and the "
                    "LLM provider keys are set in the repo-root .env."
                ),
            })
        finally:
            builtins.input = real_input
            try:
                agent_loop.close()
            except Exception:
                pass
            if ctx is not None:
                try:
                    ctx.mcp_client.close()
                except Exception:
                    pass
            # Only release the slot if this run still owns it (a takeover may
            # have already reassigned owner to a newer session).
            with _session_lock:
                if _session.owner is websocket or _session.owner is None:
                    _session.active = False
                    _session.owner = None

    _session.thread = threading.Thread(target=run, daemon=True)
    _session.thread.start()
