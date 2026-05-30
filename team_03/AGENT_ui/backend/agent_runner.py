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


class _Session:
    def __init__(self) -> None:
        self.thread: Optional[threading.Thread] = None
        self.input_queue: "queue.Queue[str]" = queue.Queue()
        self.active: bool = False


# Single active session (local single-user backend).
_session = _Session()
_session_lock = threading.Lock()


def is_active() -> bool:
    return _session.active


def submit_decision(value: str) -> None:
    """Feed a decision (chip token or free text) to the blocked checkpoint input()."""
    if _session.active:
        _session.input_queue.put(value)


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
            # Already running — treat the message as a decision instead.
            submit_decision(prompt)
            return
        _session.active = True
        _session.input_queue = queue.Queue()

    def emit(msg: Dict[str, Any]) -> None:
        """Send a WS message from the worker thread to the main event loop."""
        try:
            asyncio.run_coroutine_threadsafe(manager.send_personal(websocket, msg), loop)
        except Exception:
            pass

    def run() -> None:
        parser = CheckpointParser()
        ctx = None

        def on_line(line: str) -> None:
            parser.feed(line)

        # Patched input(): the call itself signals "menu printed, awaiting decision".
        def patched_input(prompt_text: str = "") -> str:
            payload = parser.take_checkpoint()
            emit(payload)
            # Refresh the viewport with the latest workspace layout.
            if ctx is not None:
                layout = read_session_layout(ctx.workspace_path)
                if layout:
                    emit({
                        "type": MessageType.state_update.value,
                        "field": "layout",
                        "data": layout,
                        "proposal": False,
                    })
            return _session.input_queue.get()

        import sys
        tee = StdoutTee(sys.stdout, on_line)
        real_input = builtins.input
        try:
            ctx = build_context(layout_name or "")
            from graph import build_graph, _build_initial_state

            app = build_graph(ctx)
            initial_state = _build_initial_state(prompt, ctx)

            builtins.input = patched_input
            with contextlib.redirect_stdout(tee):
                final_state = app.invoke(initial_state)

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
        except Exception as exc:  # noqa: BLE001 — surface any failure in chat
            emit({
                "type": MessageType.agent_response.value,
                "content": (
                    f"**Pipeline error:** {exc}\n\n"
                    "Check that Rhino + Swiftlet (MCP on :3002) are running and the "
                    "LLM provider keys are set in the repo-root .env."
                ),
            })
        finally:
            builtins.input = real_input
            if ctx is not None:
                try:
                    ctx.mcp_client.close()
                except Exception:
                    pass
            _session.active = False

    _session.thread = threading.Thread(target=run, daemon=True)
    _session.thread.start()
