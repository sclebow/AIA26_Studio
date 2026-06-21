"""Decision graph endpoints.

GET  /sessions/{id}/decisions              — full graph {nodes, edges, head}
GET  /sessions/{id}/decisions/{node_id}    — single node detail + children
POST /sessions/{id}/decisions/{node_id}/select
     Body: {"reason": "optional explanation"}
     Marks this node as selected (deselects siblings), advances graph head,
     appends a 'select' node as child. Returns the new select node.
"""
from __future__ import annotations

import sys
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ..decision_graph import DecisionGraph
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["decisions"])


class SelectRequest(BaseModel):
    reason: str = ""


@router.get("/{session_id}/decisions")
async def get_decision_graph(session_id: str) -> dict:
    """Return the full decision DAG as {nodes, edges, head}."""
    graph = await store.get_graph(session_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return graph.to_dict()


@router.get("/{session_id}/decisions/{node_id}")
async def get_decision_node(session_id: str, node_id: str) -> dict:
    """Return a single node plus its direct children."""
    graph = await store.get_graph(session_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Session not found")
    node = graph.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return {
        **node,
        "children": graph.children_of(node_id),
    }


@router.post("/{session_id}/decisions/{node_id}/select")
async def select_decision_node(
    session_id: str,
    node_id: str,
    body: SelectRequest,
) -> dict:
    """
    Select a specific Pareto option or branch node.

    - Marks the target node ``is_selected=True``, deselects its siblings.
    - Appends a ``select`` child node recording the choice.
    - Advances ``current_head`` to the new select node.
    - Returns the new select node.
    """
    graph = await store.get_graph(session_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Session not found")

    target = graph.get_node(node_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Node not found")

    # Mark selected + advance head to target first
    graph.select_node(node_id)

    # Append a select node as a child of the chosen node
    select_id = graph.add_node(
        "select",
        f"Selected: {target['label'][:60]}",
        parent_id=node_id,
        payload={
            "selected_node_id": node_id,
            "selected_type": target["type"],
            "reason": body.reason,
        },
    )

    await store.save_graph(session_id, graph)

    return {
        "selected_node_id": node_id,
        "select_node": graph.get_node(select_id),
        "graph_head": graph.current_head(),
    }
