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
import os
import queue
import re
import threading
from typing import Any, Dict, Optional

from websocket_manager import ConnectionManager, MessageType
from pipeline_bridge import (
    build_context,
    StdoutTee,
    CheckpointParser,
    read_session_layout,
)
import benchmark


# Graph node names → ProcessPanel card names (where they differ).
_NODE_ALIAS = {
    "path": "path_analysis",
    "user_checkpoint": "checkpoint",
}


# LangGraph super-step cap. The default (25) is too low for a full placement run:
# setup + profile + space + memory + reason↔tool loops + the 5-tool analysis
# fan-out + up to MAX_ADJUSTMENTS re-placement loops + scoring + checkpoint easily
# exceeds 25 nodes. The graph's own caps (max_iterations, MAX_ADJUSTMENTS) bound
# legitimate loops well below this, so a higher limit just lets a real run finish.
# Overridable via the GRAPH_RECURSION_LIMIT env var.
GRAPH_RECURSION_LIMIT = int(os.environ.get("GRAPH_RECURSION_LIMIT", "300"))


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

    # ── Benchmark recorder ────────────────────────────────────────────────
    # Resolve the active pipeline provider/model (UI toggle or .env default) so
    # the run is attributed to the right model for the benchmark dashboard.
    try:
        from pipeline_bridge import get_pipeline_provider, get_pipeline_model
        from _runtime.config import load_settings as _load_settings
        _settings = _load_settings()
        _bench_provider = get_pipeline_provider() or _settings.llm_provider
        _bench_model = get_pipeline_model() or _settings.llm_model
    except Exception:
        _bench_provider, _bench_model = None, None
    rec = benchmark.BenchRunRecorder(prompt, layout_name, _bench_provider, _bench_model)

    def emit(msg: Dict[str, Any]) -> None:
        """Send a WS message from the worker thread to the main event loop."""
        try:
            asyncio.run_coroutine_threadsafe(manager.send_personal(websocket, msg), loop)
        except Exception:
            pass

    def emit_event(node: str, status: str, data: Any = None) -> None:
        """Emit a per-node pipeline event (drives the Pipeline panel + Log)."""
        # Feed the benchmark recorder with raw (un-aliased) node timings. `setup`
        # streams granular progress as repeated "completed" lines, so skip it.
        if node != "setup":
            try:
                if status == "started":
                    rec.node_started(node)
                elif status == "completed":
                    rec.node_completed(node)
                elif status == "error":
                    rec.node_error(node, str(data or ""))
            except Exception:
                pass
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
        try:
            rec.set_scoring(overall, grade, breakdown)
        except Exception:
            pass

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
        bench_status = {"v": "ok"}

        def on_line(line: str) -> None:
            parser.feed(line)
            # Stream zone planning summary lines to the UI as agent_say events
            stripped = line.strip()
            if stripped.startswith("[populate_agent] Phase 1 complete:"):
                emit({"type": MessageType.agent_say.value,
                      "content": f"📋 {stripped.replace('[populate_agent] ', '')}"})
            elif stripped.startswith("  - ") and state.get("current_node") == "populate_agent":
                emit({"type": MessageType.agent_say.value,
                      "content": stripped})
            elif stripped.startswith("[populate_agent] Phase 2:"):
                emit({"type": MessageType.agent_say.value,
                      "content": "📐 Calculating coordinates for first zone..."})
            elif stripped.startswith("[zone] Advancing to:"):
                emit({"type": MessageType.agent_say.value,
                      "content": f"➡️ {stripped.replace('[zone] ', '')}"})
            elif stripped.startswith("[zone] Calculating coordinates for:"):
                emit({"type": MessageType.agent_say.value,
                      "content": f"📐 {stripped.replace('[zone] ', '')}"})


        # Patched input(): the call itself signals "menu printed, awaiting decision".
        def patched_input(prompt_text: str = "") -> str:
            payload = parser.take_checkpoint()
            try:
                rec.note_checkpoint()
            except Exception:
                pass
            # Strip raw JSON bleed from agent message — happens when LLM
            # outputs markdown+JSON mixed instead of pure JSON
            agent_msg = payload.get("agentMessage", "") or ""
            # Remove everything from the first { that looks like a JSON blob
            clean_msg = re.split(r'\s*\{\"action\"', agent_msg)[0].strip()
            # Also strip trailing raw JSON object if present
            clean_msg = re.sub(r'\{[\s\S]*\}[\s\}]*$', '', clean_msg).strip()
            if clean_msg:
                payload["agentMessage"] = clean_msg
            elif not clean_msg and agent_msg:
                # Entire message was JSON — suppress it
                payload["agentMessage"] = ""
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
            async for ev in app.astream_events(
                initial_state,
                config={"recursion_limit": GRAPH_RECURSION_LIMIT},
                version="v2",
            ):
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

                        # Collision node → push grid-based heatmap to the 3D viewport.
                        # The pipeline's collision_results still carry _grid_meta (the
                        # adapter only moves it to grid_viz for the HTTP path).
                        if node == "collision":
                            cr = out.get("collision_results") or {}
                            gm = cr.get("_grid_meta") or cr.get("grid_viz")
                            if gm and (gm.get("violation_cells") or gm.get("warning_cells")):
                                emit({
                                    "type": MessageType.analysis_overlay.value,
                                    "kind": "collision",
                                    "grid_viz": {
                                        "violation_cells": gm.get("violation_cells", []),
                                        "warning_cells":   gm.get("warning_cells",   []),
                                        "ox":   gm.get("ox",   0),
                                        "oy":   gm.get("oy",   0),
                                        "cols": gm.get("cols", 0),
                                        "rows": gm.get("rows", 0),
                                        "cs":   gm.get("cs",   0.10),
                                    },
                                })

                        # Orientation node → push arrow data for each object.
                        elif node == "orientation":
                            or_r = out.get("orientation_results") or {}
                            results = or_r.get("results", [])
                            if results:
                                emit({
                                    "type": MessageType.analysis_overlay.value,
                                    "kind": "orientation",
                                    "results": results,
                                })
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

            # If the run was approved, the output node saved a timestamped revision
            # to team_03/output/. Tell the UI so it refreshes the Version History
            # panel and switches the viewport to the newly-saved version.
            try:
                m = re.search(r"saved to\s+(.+\.json)", str(final_response))
                if m:
                    from pathlib import Path as _Path
                    saved = _Path(m.group(1).strip().strip('"').strip("'"))
                    emit({
                        "type": MessageType.version_saved.value,
                        "file": saved.name,
                        "id": saved.stem,
                        "name": (ctx.layout_name if ctx else None),
                    })
            except Exception:
                pass

            # Strip the "final_response" prefix if the explain node prepended it
            clean_response = str(final_response)
            if clean_response.startswith("final_response"):
                clean_response = clean_response[len("final_response"):].strip()
            print(f"[debug] Emitting final response ({len(clean_response)} chars): {clean_response[:200]}")

            async def _delayed_response_emit():
                await asyncio.sleep(1.5)
                emit({"type": MessageType.agent_response.value, "content": clean_response})
            asyncio.run_coroutine_threadsafe(_delayed_response_emit(), loop)

            # Emit final layout — try workspace first, fall back to state
            layout = read_session_layout(ctx.workspace_path)
            if not layout:
                try:
                    layout_str = (final_state or {}).get("layout_json_string")
                    if layout_str:
                        import json as _json
                        layout = _json.loads(layout_str)
                except Exception:
                    pass
            if layout:
                import asyncio as _asyncio
                async def _delayed_layout_emit():
                    await _asyncio.sleep(1.0)
                    emit({
                        "type": MessageType.state_update.value,
                        "field": "layout",
                        "data": layout,
                        "proposal": False,
                    })
                asyncio.run_coroutine_threadsafe(_delayed_layout_emit(), loop)
                # Also emit scores if available so dashboard stays populated
                sr = (final_state or {}).get("scoring_results") or {}
                if sr.get("total_score") is not None:
                    emit_scores(
                        sr.get("total_score"),
                        sr.get("grade"),
                        sr.get("breakdown") or {},
                    )

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
            bench_status["v"] = "ok"
        except _Aborted:
            # Client disconnected / superseded — unwind quietly, no chat error.
            bench_status["v"] = "aborted"
        except Exception as exc:  # noqa: BLE001 — surface any failure in chat + panel
            bench_status["v"] = "error"
            if "recursion" in str(exc).lower():
                try:
                    rec.note_recursion_hit()
                except Exception:
                    pass
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
            # Finalize the benchmark record (always — ok / aborted / error) and
            # notify the UI so the Benchmark dashboard refreshes live.
            try:
                run_record = rec.finalize(bench_status["v"])
                emit({"type": MessageType.benchmark_update.value, "run": run_record})
            except Exception as exc:
                print(f"[benchmark] finalize failed: {exc}")
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
