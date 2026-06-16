"""Chat endpoint with SSE streaming + decision graph node creation.

POST /sessions/{id}/chat
    Body:  {"message": "...", "tags": [...]}
    Returns: SSE stream

SSE event types:
  token        — partial assistant text token
  tool         — tool call fired (name + condensed args)
  decision     — a new decision graph node was created {node_id, type, label}
  state        — final AgentState JSON after completion
  error        — error string
  done         — end of stream (empty data)

Decision graph hooks
--------------------
  1. User message     → intent node (immediately, before agent runs)
  1b. extract_brief end → brief node (Phase 0 comprehension, before any tool)
  2. on_tool_start    → action node per tool call
  3. Pareto results   → branch node with one state-child per option
  4. place_building   → state node with building snapshot
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
    make_action_node,
    make_branch_nodes,
    make_state_node,
)
from ..schemas import ChatRequest
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["chat"])

# Tool names that represent the Pareto optimizer generating alternatives
_BRANCH_TOOLS = {"optimize_view_placement", "optimize_two_building_placement"}
# Tool name that represents a building being placed
_PLACE_TOOLS = {"place_building", "generate_building_boundary"}


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

        current_action_parent = intent_id   # action/brief nodes hang off the intent
        full_response = ""
        brief_emitted = False                # Phase 0 brief node — at most one per turn

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
                data = event.get("data", {})

                # LLM token streaming
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

                # 2. Tool start → action node
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "")
                    input_preview = str(data.get("input", ""))[:150]
                    action_id = make_action_node(
                        graph, tool_name, input_preview, current_action_parent
                    )
                    current_action_parent = action_id
                    yield {
                        "event": "tool",
                        "data": json.dumps({"name": tool_name, "input_preview": input_preview}),
                    }
                    yield {
                        "event": "decision",
                        "data": json.dumps(_node_event(graph.get_node(action_id))),
                    }

                # 3. Tool end → check for Pareto solutions or placed buildings
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "")
                    output = data.get("output", {})
                    output_dict = _try_parse(output)

                    # Pareto branch
                    pareto = _extract_pareto(output_dict, tool_name)
                    if pareto and len(pareto) > 1:
                        branch_id = make_branch_nodes(graph, current_action_parent, pareto)
                        yield {
                            "event": "decision",
                            "data": json.dumps(_node_event(graph.get_node(branch_id))),
                        }

                    # Place building
                    elif tool_name in _PLACE_TOOLS:
                        placed = _extract_placed(output_dict, state)
                        if placed:
                            state_id = make_state_node(graph, current_action_parent, placed)
                            yield {
                                "event": "decision",
                                "data": json.dumps(_node_event(graph.get_node(state_id))),
                            }

                # 1b. extract_brief node end → Phase 0 comprehension node.
                # The node runs first (START → extract_brief → planner), so the
                # current parent is still the intent. It returns ``design_brief``
                # only when it freshly comprehends (idempotent pass-through
                # returns ``{}``), so its presence is the "new brief" signal.
                elif (
                    kind == "on_chain_end"
                    and event.get("name") == "extract_brief"
                    and not brief_emitted
                ):
                    node_output = data.get("output", {})
                    brief_payload = (
                        node_output.get("design_brief")
                        if isinstance(node_output, dict) else None
                    )
                    if isinstance(brief_payload, dict):
                        brief_id = make_brief_node(
                            graph, brief_payload, current_action_parent
                        )
                        current_action_parent = brief_id   # actions now hang off the brief
                        brief_emitted = True
                        yield {
                            "event": "decision",
                            "data": json.dumps(_node_event(graph.get_node(brief_id))),
                        }

                    # The agent paused to ask the user back → emit a clarify node.
                    clar_req = (
                        node_output.get("clarification_request")
                        if isinstance(node_output, dict) else None
                    )
                    if isinstance(clar_req, dict) and clar_req.get("fields"):
                        clarify_id = make_clarify_node(graph, clar_req, current_action_parent)
                        current_action_parent = clarify_id
                        yield {
                            "event": "clarify",
                            "data": json.dumps(clar_req),
                        }
                        yield {
                            "event": "decision",
                            "data": json.dumps(_node_event(graph.get_node(clarify_id))),
                        }

                # Final graph output
                elif kind == "on_chain_end" and event.get("name") == "LangGraph":
                    final_state = data.get("output", state)
                    await store.update_state(session_id, final_state)
                    await store.save_graph(session_id, graph)

                    final_response = final_state.get("final_response") or full_response
                    await store.append_message(session_id, "assistant", final_response)

                    yield {
                        "event": "state",
                        "data": json.dumps(_safe_state(final_state)),
                    }

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
