"""Chat endpoint with SSE streaming + decision graph node creation.

POST /sessions/{id}/chat   Body: {"message": "...", "tags": [...]}   -> SSE stream

SSE event types:
  token     — partial assistant text token
  tool      — a tool call fired {name, input_preview}
  decision  — a new decision graph node {node_id, type, label, parent_id, is_selected}
  state     — final AgentState (condensed) after completion
  error     — error string (e.g. agent not configured)
  done      — end of stream

Decision graph growth:
  1. user message  -> intent node (immediately)
  2. on_tool_start -> action node per tool call
  3. Pareto output -> branch node + one state-child per option
  4. building placed -> state node

The agent itself is the REAL one, built by connection.agent_runtime (same wiring
as agent/main.py). We do NOT reimplement any agent behaviour here.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from ..decision_graph import (
    DecisionGraph,
    make_action_node,
    make_branch_nodes,
    make_intent_node,
    make_state_node,
)
from ..schemas import ChatRequest
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["chat"])

_BRANCH_TOOLS = {"optimize_view_placement", "optimize_two_building_placement"}
_PLACE_TOOLS = {"place_building", "generate_building_boundary", "import_building_boundary"}


@router.post("/{session_id}/chat")
async def chat(session_id: str, body: ChatRequest, request: Request) -> EventSourceResponse:
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    await store.append_message(session_id, "user", body.message, body.tags)

    async def event_generator():
        graph = await store.get_graph(session_id) or DecisionGraph()

        # 1. intent node
        intent_id = make_intent_node(graph, body.message)
        yield {"event": "decision", "data": json.dumps(_node_event(graph.get_node(intent_id)))}

        current_parent = intent_id
        full_response = ""

        try:
            # Build (or reuse) the real compiled agent graph. If the environment
            # isn't configured this raises — surfaced as an SSE error, not a stub.
            from ..agent_runtime import get_graph

            agent_graph = get_graph()

            state = dict(await store.get_state(session_id) or {})
            state["user_prompt"] = body.message
            state["messages"] = list(state.get("messages", [])) + [f"User: {body.message}"]

            async for event in agent_graph.astream_events(state, version="v2"):
                if await request.is_disconnected():
                    break

                kind = event.get("event", "")
                data = event.get("data", {})

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

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "")
                    input_preview = str(data.get("input", ""))[:150]
                    action_id = make_action_node(graph, tool_name, input_preview, current_parent)
                    current_parent = action_id
                    yield {"event": "tool", "data": json.dumps({"name": tool_name, "input_preview": input_preview})}
                    yield {"event": "decision", "data": json.dumps(_node_event(graph.get_node(action_id)))}

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "")
                    output_dict = _try_parse(data.get("output", {}))

                    pareto = _extract_pareto(output_dict, tool_name)
                    if pareto and len(pareto) > 1:
                        branch_id = make_branch_nodes(graph, current_parent, pareto)
                        yield {"event": "decision", "data": json.dumps(_node_event(graph.get_node(branch_id)))}
                        for child in graph.children_of(branch_id):
                            yield {"event": "decision", "data": json.dumps(_node_event(child))}
                    elif tool_name in _PLACE_TOOLS:
                        placed = _extract_placed(output_dict, state)
                        if placed:
                            state_id = make_state_node(graph, current_parent, placed)
                            yield {"event": "decision", "data": json.dumps(_node_event(graph.get_node(state_id)))}

                elif kind == "on_chain_end" and event.get("name") in ("LangGraph", "__start__"):
                    final_state = data.get("output", state)
                    if isinstance(final_state, dict):
                        await store.update_state(session_id, final_state)
                        full_response = final_state.get("final_response") or full_response
                        state = final_state

            # Stamp parsed program (floors→height, use) onto each placed building so
            # the explorer/viewer show storeys and wing floor counts. The agent state
            # itself doesn't carry height; we derive it from the user's prompt.
            _stamp_program(state, body.message)

            await store.update_state(session_id, state)
            await store.append_message(session_id, "assistant", full_response or "Done.")
            await store.save_graph(session_id, graph)
            yield {"event": "state", "data": json.dumps(_safe_state(state))}
            yield {"event": "done", "data": ""}

        except Exception as exc:  # noqa: BLE001
            await store.save_graph(session_id, graph)
            yield {"event": "error", "data": str(exc)}
            yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _stamp_program(state: dict, prompt: str) -> None:
    """Derive floors→height and building use from the prompt and stamp them onto
    each placed building (the agent state has no height field)."""
    try:
        from ..notebook_logic.agent_runtime import parse_program

        program = parse_program(prompt or "")
    except Exception:  # noqa: BLE001
        return
    if not program.get("height_m"):
        return
    for bld in state.get("placed_buildings", []) or []:
        if isinstance(bld, dict):
            bld.setdefault("height_m", program["height_m"])
            if program.get("building_use"):
                bld.setdefault("building_use", program["building_use"])


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
        except Exception:  # noqa: BLE001
            pass
    return {}


def _extract_pareto(output: dict, tool_name: str) -> list[dict]:
    if tool_name not in _BRANCH_TOOLS:
        return []
    data = output.get("data", output) if isinstance(output, dict) else {}
    if isinstance(data, dict):
        return data.get("pareto_solutions", []) or output.get("pareto_solutions", [])
    return output.get("pareto_solutions", [])


def _extract_placed(output: dict, state: dict) -> list[dict]:
    placed = output.get("placed_buildings") or state.get("placed_buildings", [])
    return placed if isinstance(placed, list) else []


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
