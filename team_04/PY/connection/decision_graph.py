"""Decision graph — tracks the design process as a DAG.

Each session has one DecisionGraph. Nodes represent meaningful design moments;
edges represent causation. The frontend receives
``{nodes: [...], edges: [{source, target}], head}`` — directly consumable by a
DAG renderer without transformation.

Node types
----------
  intent  — user sends a chat message
  action  — a tool fires
  branch  — optimizer returns Pareto solutions; children = one per option
  select  — user picks an option from the explorer panel
  state   — building placed; geometry snapshot stored

This module matches the contract the notebooks import as
``from backend.decision_graph import DecisionGraph, make_intent_node, ...``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


class DecisionGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._head: str | None = None

    # ------------------------------------------------------------------ #
    # Mutation
    # ------------------------------------------------------------------ #
    def add_node(
        self,
        node_type: str,
        label: str,
        *,
        parent_id: str | None = None,
        payload: dict[str, Any] | None = None,
        is_selected: bool = True,
    ) -> str:
        node_id = str(uuid.uuid4())
        node: dict[str, Any] = {
            "node_id": node_id,
            "parent_id": parent_id,
            "type": node_type,
            "label": label[:120],
            "timestamp": _now_iso(),
            "is_selected": is_selected,
            "payload": payload or {},
        }
        self._nodes[node_id] = node
        if is_selected:
            self._head = node_id
        return node_id

    def select_node(self, node_id: str) -> bool:
        node = self._nodes.get(node_id)
        if node is None:
            return False
        parent_id = node.get("parent_id")
        if parent_id:
            for n in self._nodes.values():
                if n.get("parent_id") == parent_id and n["node_id"] != node_id:
                    n["is_selected"] = False
        node["is_selected"] = True
        self._head = node_id
        return True

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #
    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    def children_of(self, node_id: str) -> list[dict[str, Any]]:
        return [n for n in self._nodes.values() if n.get("parent_id") == node_id]

    def current_head(self) -> str | None:
        return self._head

    def node_count(self) -> int:
        return len(self._nodes)

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        nodes = list(self._nodes.values())
        edges = [
            {
                "id": f"{n['parent_id']}-{n['node_id']}",
                "source": n["parent_id"],
                "target": n["node_id"],
            }
            for n in nodes
            if n.get("parent_id")
        ]
        return {"nodes": nodes, "edges": edges, "head": self._head}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionGraph":
        g = cls()
        for n in data.get("nodes", []):
            g._nodes[n["node_id"]] = n
        g._head = data.get("head")
        return g


# --------------------------------------------------------------------------- #
# Helpers — used by the chat router to grow the graph during a turn.
# --------------------------------------------------------------------------- #

def make_intent_node(graph: DecisionGraph, message: str) -> str:
    return graph.add_node(
        "intent",
        f"User: {message[:80]}",
        parent_id=graph.current_head(),
        payload={"user_message": message},
    )


def make_action_node(
    graph: DecisionGraph,
    tool_name: str,
    input_preview: str,
    parent_id: str | None,
) -> str:
    return graph.add_node(
        "action",
        f"Tool: {tool_name}",
        parent_id=parent_id,
        payload={"tool_name": tool_name, "input_preview": input_preview[:200]},
    )


def make_branch_nodes(
    graph: DecisionGraph,
    parent_id: str | None,
    pareto_solutions: list[dict[str, Any]],
) -> str:
    branch_id = graph.add_node(
        "branch",
        f"Pareto alternatives ({len(pareto_solutions)} options)",
        parent_id=parent_id,
        payload={"option_count": len(pareto_solutions)},
        is_selected=False,
    )
    for opt in pareto_solutions:
        rank = opt.get("rank", "?")
        score = opt.get("combined_score", opt.get("avg_combined_score", 0.0))
        try:
            score_text = f"{float(score):.3f}"
        except (TypeError, ValueError):
            score_text = str(score)
        graph.add_node(
            "state",
            f"Option {rank} (score={score_text})",
            parent_id=branch_id,
            payload={
                "option_id": opt.get("option_id", f"option_{rank}"),
                "combined_score": score,
                "boundary": opt.get("boundary"),
                "rotation_degrees": opt.get("rotation_degrees"),
                "centroid_xy": opt.get("centroid_xy"),
            },
            is_selected=False,
        )
    return branch_id


def make_state_node(
    graph: DecisionGraph,
    parent_id: str | None,
    placed_buildings: list[dict[str, Any]],
) -> str:
    snapshots = [
        {
            "label": b.get("label", f"Building {i + 1}"),
            "boundary": b.get("boundary") or b.get("building_boundary"),
            "area_sqm": None,
        }
        for i, b in enumerate(placed_buildings)
    ]
    return graph.add_node(
        "state",
        f"{len(placed_buildings)} building(s) placed",
        parent_id=parent_id,
        payload={"building_count": len(placed_buildings), "building_snapshots": snapshots},
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
