"""Decision-graph routes — graph / select node / add option.

Thin wrappers over connection.notebook_logic.decision_graph_runtime. The graph is
persisted to connection/data/decision_graph.json so it survives across requests
(single shared design graph, matching the confirmed-site single-source pattern).
"""
from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..notebook_logic import decision_graph_runtime as dg

router = APIRouter(prefix="/api/decision-graph", tags=["api-decision-graph"])

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
_GRAPH_PATH = os.path.join(_DATA_DIR, "decision_graph.json")


def _load() -> Any:
    if os.path.exists(_GRAPH_PATH):
        try:
            with open(_GRAPH_PATH, encoding="utf-8") as fh:
                return dg.from_payload(json.load(fh))
        except (json.JSONDecodeError, OSError):
            pass
    return dg.new_graph()


def _save(graph: Any) -> dict[str, Any]:
    os.makedirs(_DATA_DIR, exist_ok=True)
    payload = dg.to_frontend_payload(graph)
    with open(_GRAPH_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return payload


class OptionRequest(BaseModel):
    options: list[dict[str, Any]] = Field(description="Candidate/Pareto options to branch on.")
    parent_id: str | None = None


class SelectRequest(BaseModel):
    node_id: str


@router.get("")
def get_graph() -> dict[str, Any]:
    return dg.to_frontend_payload(_load())


@router.delete("")
def reset_graph() -> dict[str, Any]:
    if os.path.exists(_GRAPH_PATH):
        os.remove(_GRAPH_PATH)
    return {"reset": True, "graph": dg.to_frontend_payload(dg.new_graph())}


@router.post("/option")
def add_option(body: OptionRequest) -> dict[str, Any]:
    graph = _load()
    branch_id = dg.branch_options(graph, body.options, parent_id=body.parent_id)
    return {"branch_id": branch_id, "graph": _save(graph)}


@router.post("/select")
def select_node(body: SelectRequest) -> dict[str, Any]:
    graph = _load()
    if not dg.select_path(graph, body.node_id):
        raise HTTPException(status_code=404, detail="Node not found")
    return {"selected_node_id": body.node_id, "graph": _save(graph)}
