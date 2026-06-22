"""Chat endpoint with SSE streaming + decision graph node creation.

POST /sessions/{id}/chat
    Body:  {"message": "...", "tags": [...]}
    Returns: SSE stream

SSE event types (the live ReAct trace the UI renders step by step):
  token        — partial assistant text token (transient "typing" shimmer)
  thought      — supervisor reasoning: {action, reasoning}
  tool         — a tool finished firing: {name, input_preview, count}
                 (count = how many times the agent has used that tool this turn)
  tool_result  — that tool's outcome: {name, ok, summary, count}
  validation   — self-validation verdict: {passed, failures, summary, metrics}
  retry        — a self-debug attempt: {attempt, directive, diagnosis, failures}
  decision     — a new decision graph node was created {node_id, type, label}
  clarify      — the agent paused to ask the user back (clarification request)
  state        — final AgentState JSON after completion
  error        — error string
  done         — end of stream (empty data)

Why everything hangs off ``on_chain_end``
-----------------------------------------
The agent's tools are plain Python calls inside graph nodes, NOT LangChain
``Tool`` objects, so ``astream_events`` never emits ``on_tool_start`` /
``on_tool_end``. Instead each node returns a state-update dict, surfaced as
``on_chain_end`` with ``event["name"] == <node name>``. We diff that output to
emit the trace:

  * user message            → intent node (immediately, before the agent runs)
  * extract_brief end       → brief node (Phase 0 comprehension)
  * central_reason end      → thought event + node (the "Reason" step)
  * any node's tool_history → action node(s) + tool / tool_result events (+count)
  * validate end            → validation event + validate node
  * debug end               → retry event + retry node (self-correction)
  * Pareto tool output      → branch node with one state-child per option
  * place_building end       → state node with the placed-building snapshot
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ..decision_graph import (
    DecisionGraph,
    make_intent_node,
    make_brief_node,
    make_clarify_node,
    make_thought_node,
    make_action_node,
    make_validate_node,
    make_retry_node,
    make_branch_nodes,
    make_state_node,
)
from ..schemas import ChatRequest
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["chat"])

# Tool names that represent the Pareto optimizer generating alternatives
_BRANCH_TOOLS = {"optimize_view_placement", "optimize_two_building_placement"}

# Graph node names whose on_chain_end output we inspect for the live trace.
_AGENT_NODES = {
    "extract_brief", "central_reason", "read_site", "generate_shape",
    "check_requested_position", "check_constraints", "validate", "debug",
    "optimize", "evaluate", "place_building", "analyze_remaining_positions",
    "await_human", "report",
}


@router.post("/{session_id}/chat")
async def chat(
    session_id: str,
    body: ChatRequest,
    request: Request,
) -> EventSourceResponse:
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Record user message in chat history
    await store.append_message(session_id, "user", body.message, body.tags)

    async def event_generator():
        graph = await store.get_graph(session_id)
        if graph is None:
            graph = DecisionGraph()

        # 1. Intent node — created immediately from user message
        intent_id = make_intent_node(graph, body.message)
        yield {
            "event": "decision",
            "data": json.dumps(_node_event(graph.get_node(intent_id))),
        }

        parent = intent_id                   # every new node hangs off this pointer
        full_response = ""
        brief_emitted = False                # Phase 0 brief node — at most one per turn
        seen_tool_len = 0                    # tool_history records already surfaced
        tool_counts: dict[str, int] = {}     # running per-tool call counter

        def _emit_node(node_id: str):
            """Helper: build the SSE 'decision' payload for a freshly made node."""
            return {"event": "decision", "data": json.dumps(_node_event(graph.get_node(node_id)))}

        try:
            state = await store.get_state(session_id)
            state = dict(state)
            state["user_prompt"] = body.message
            state["messages"] = state.get("messages", []) + [f"User: {body.message}"]

            from ..agent_runtime import get_agent_app
            graph_agent = get_agent_app()

            async for event in graph_agent.astream_events(state, version="v2"):
                if await request.is_disconnected():
                    break

                kind = event.get("event", "")
                name = event.get("name", "")
                data = event.get("data", {})

                # ── LLM token streaming (transient typing shimmer) ──────────────
                if kind == "on_chat_model_stream":
                    chunk = data.get("chunk", {})
                    token = (
                        chunk.content if hasattr(chunk, "content")
                        else chunk.get("content", "") if isinstance(chunk, dict)
                        else ""
                    )
                    if token:
                        full_response += token
                        yield {"event": "token", "data": token}
                    continue

                # ── Final graph output ──────────────────────────────────────────
                if kind == "on_chain_end" and name == "LangGraph":
                    final_state = data.get("output", state)
                    await store.update_state(session_id, final_state)
                    await store.save_graph(session_id, graph)
                    final_response = final_state.get("final_response") or full_response
                    await store.append_message(session_id, "assistant", final_response)
                    yield {"event": "state", "data": json.dumps(_safe_state(final_state))}
                    continue

                # Everything else of interest is a node finishing.
                if kind != "on_chain_end" or name not in _AGENT_NODES:
                    continue
                output = data.get("output", {})
                if not isinstance(output, dict):
                    continue

                # ── 1b. extract_brief → Phase 0 brief node (+ clarify) ──────────
                if name == "extract_brief":
                    brief_payload = output.get("design_brief")
                    if isinstance(brief_payload, dict) and not brief_emitted:
                        parent = make_brief_node(graph, brief_payload, parent)
                        brief_emitted = True
                        yield _emit_node(parent)
                    clar_req = output.get("clarification_request")
                    if isinstance(clar_req, dict) and clar_req.get("fields"):
                        parent = make_clarify_node(graph, clar_req, parent)
                        yield {"event": "clarify", "data": json.dumps(clar_req)}
                        yield _emit_node(parent)

                # ── Reason step: the supervisor's chosen action + why ───────────
                if name == "central_reason":
                    action = str(output.get("current_action", "")).strip()
                    reasoning = str(output.get("decision_reason", "")).strip()
                    if action:
                        parent = make_thought_node(graph, action, reasoning, parent)
                        yield {"event": "thought", "data": json.dumps({"action": action, "reasoning": reasoning})}
                        yield _emit_node(parent)

                # ── Any newly recorded tool calls → action nodes + events ───────
                tool_history = output.get("tool_history")
                if isinstance(tool_history, list) and len(tool_history) > seen_tool_len:
                    for record in tool_history[seen_tool_len:]:
                        if not isinstance(record, dict):
                            continue
                        tool_name = str(record.get("tool", "")).strip() or "tool"
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                        count = tool_counts[tool_name]
                        out = record.get("output")
                        ok = _output_ok(out)
                        summary = _summarize_output(out)
                        input_preview = json.dumps(record.get("arguments", {}))[:150]

                        parent = make_action_node(
                            graph, tool_name, input_preview, parent,
                            call_count=count, result_summary=summary, ok=ok,
                        )
                        yield {"event": "tool", "data": json.dumps(
                            {"name": tool_name, "input_preview": input_preview, "count": count})}
                        yield {"event": "tool_result", "data": json.dumps(
                            {"name": tool_name, "ok": ok, "summary": summary, "count": count})}
                        yield _emit_node(parent)

                        # Pareto optimizer → branch with one option per child.
                        pareto = _extract_pareto(_try_parse(out), tool_name)
                        if pareto and len(pareto) > 1:
                            branch_id = make_branch_nodes(graph, parent, pareto)
                            yield _emit_node(branch_id)
                    seen_tool_len = len(tool_history)

                # ── Self-validation verdict ─────────────────────────────────────
                if name == "validate" and isinstance(output.get("validation_result"), dict):
                    validation = output["validation_result"]
                    parent = make_validate_node(graph, validation, parent)
                    yield {"event": "validation", "data": json.dumps({
                        "passed": bool(output.get("validation_passed", validation.get("passed", False))),
                        "failures": validation.get("failures", []),
                        "summary": validation.get("summary", ""),
                        "metrics": validation.get("metrics", {}),
                        "judge": validation.get("judge"),
                    })}
                    yield _emit_node(parent)

                # ── Self-debug attempt (the agent correcting itself) ────────────
                if name == "debug" and output.get("debug_history"):
                    history = output["debug_history"]
                    latest = history[-1] if isinstance(history, list) and history else {}
                    if isinstance(latest, dict):
                        parent = make_retry_node(
                            graph, int(latest.get("attempt", output.get("debug_attempts", 1))),
                            str(latest.get("directive", "")), parent,
                            diagnosis=str(latest.get("diagnosis", "")),
                            failures=latest.get("failures", []),
                        )
                        yield {"event": "retry", "data": json.dumps(latest)}
                        yield _emit_node(parent)

                # ── Building placed → state snapshot node ───────────────────────
                if name == "place_building":
                    placed = output.get("placed_buildings")
                    if isinstance(placed, list) and placed:
                        parent = make_state_node(graph, parent, placed)
                        yield _emit_node(parent)

            # Persist graph even if chain_end event was missed
            await store.save_graph(session_id, graph)
            yield {"event": "done", "data": ""}

        except Exception as exc:
            await store.save_graph(session_id, graph)
            yield {"event": "error", "data": str(exc)}
            yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node_event(node: dict | None) -> dict:
    if node is None:
        return {}
    return {
        "node_id": node["node_id"],
        "type": node["type"],
        "label": node["label"],
        "parent_id": node.get("parent_id"),
        "is_selected": node.get("is_selected", True),
    }


def _try_parse(output: Any) -> dict:
    if isinstance(output, dict):
        return output
    if isinstance(output, str):
        try:
            return json.loads(output)
        except Exception:
            pass
    return {}


def _extract_pareto(output: dict, tool_name: str) -> list[dict]:
    if tool_name not in _BRANCH_TOOLS:
        return []
    return output.get("pareto_solutions", [])


def _output_ok(output: Any) -> bool:
    """Best-effort success flag for a tool's parsed output."""
    parsed = _try_parse(output)
    if isinstance(parsed, dict):
        if "success" in parsed:
            return bool(parsed["success"])
        if "error" in parsed and parsed["error"]:
            return False
    return True


def _summarize_output(output: Any) -> str:
    """One-line, human-readable digest of a tool result for the activity feed."""
    parsed = _try_parse(output)
    if not isinstance(parsed, dict):
        text = str(output)
        return text[:160]
    data = parsed.get("data", parsed)
    if not isinstance(data, dict):
        return str(data)[:160]
    # Validator result is the most informative — surface its verdict.
    if "passed" in data and "failures" in data:
        verdict = "passed" if data.get("passed") else f"failed ({', '.join(data.get('failures', [])) or '—'})"
        return f"validation {verdict}"
    if isinstance(data.get("summary"), str) and data["summary"]:
        return data["summary"][:160]
    keys = [k for k in ("geometry_id", "shape_type", "boundary", "candidate_positions", "fits_within_site_boundary") if k in data]
    if keys:
        bits = []
        for k in keys:
            v = data[k]
            if isinstance(v, list):
                bits.append(f"{k}={len(v)} pts")
            else:
                bits.append(f"{k}={v}")
        return ", ".join(bits)[:160]
    return (str(data)[:160]) if data else "ok"


def _safe_state(state: dict) -> dict:
    return {
        "placed_buildings": state.get("placed_buildings", []),
        "site_boundary": state.get("site_boundary", []),
        "site_context": state.get("site_context", {}),
        "final_response": state.get("final_response"),
        "violations": state.get("violations", []),
        "optimization_cycles": state.get("optimization_cycles", 0),
        "error": state.get("error"),
    }
