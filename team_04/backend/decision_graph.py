"""Decision graph — tracks the design process as a DAG.

Each session has one DecisionGraph.  Nodes represent meaningful design
moments; edges represent causation.  The frontend receives
``{nodes: [...], edges: [{source, target}]}`` — directly consumable by
React Flow or D3-DAG without transformation.

Node types
----------
  intent  — user sends a chat message
  brief   — Phase 0 comprehension: the typed DesignBrief extracted from the
            prompt (count, shapes, courtyard, objective weights). Sits between
            the user intent and the first action so the rest of the chain is
            explained by what the agent *understood*, not by re-parsing text.
  clarify — the agent paused to ask the user back: a structured question
            (shape / side / view-side / size / use / count) raised when a
            placement-critical field is missing. Carries the clarification
            request payload; the UI renders it as chips and POSTs answers.
  action  — a tool fires (grouped per LangGraph step, not per micro-call)
  branch  — optimizer returns Pareto solutions; children = one per option
  select  — user picks an option from the explorer panel
  state   — building placed; geometry snapshot stored

Branching
---------
When the Pareto optimizer runs it creates a ``branch`` node and one
``state`` child per option.  The user can later POST /select on any child,
which marks it ``is_selected=True`` and advances ``_head`` — forking the
design history.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


class DecisionGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}   # node_id → node dict
        self._head: str | None = None                  # most recently selected/created node

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_node(
        self,
        node_type: str,
        label: str,
        *,
        parent_id: str | None = None,
        payload: dict[str, Any] | None = None,
        is_selected: bool = True,
    ) -> str:
        """Create a node and return its id.

        ``is_selected=True`` (default) marks this as the active path and
        advances the head pointer.  Pass ``is_selected=False`` for branch
        children that haven't been chosen yet.
        """
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
        """Mark a node as selected and advance the head.  Returns False if not found."""
        node = self._nodes.get(node_id)
        if node is None:
            return False
        # Deselect all siblings (same parent)
        parent_id = node.get("parent_id")
        if parent_id:
            for n in self._nodes.values():
                if n.get("parent_id") == parent_id and n["node_id"] != node_id:
                    n["is_selected"] = False
        node["is_selected"] = True
        self._head = node_id
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    def children_of(self, node_id: str) -> list[dict[str, Any]]:
        return [n for n in self._nodes.values() if n.get("parent_id") == node_id]

    def current_head(self) -> str | None:
        return self._head

    def node_count(self) -> int:
        return len(self._nodes)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return {nodes, edges} ready for React Flow / D3-DAG."""
        nodes = list(self._nodes.values())
        edges = [
            {"id": f"{n['parent_id']}-{n['node_id']}",
             "source": n["parent_id"],
             "target": n["node_id"]}
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_intent_node(graph: DecisionGraph, message: str) -> str:
    return graph.add_node(
        "intent",
        f"User: {message[:80]}",
        parent_id=graph.current_head(),
        payload={"user_message": message},
    )


def make_brief_node(
    graph: DecisionGraph,
    brief: dict[str, Any],
    parent_id: str | None,
    *,
    label: str | None = None,
) -> str:
    """Phase 0 reasoning node — the typed DesignBrief the agent comprehended.

    ``brief`` is a ``DesignBrief.to_state()`` dict. The node sits between the
    user ``intent`` and the first ``action``: it records *what the agent
    understood* (building count, per-building shapes, courtyard, objective
    weights, source = llm|fallback) so the downstream chain reads as the
    consequence of comprehension rather than re-parsing the raw prompt.
    """
    count = brief.get("building_count", 1)
    shapes = [b.get("shape_preference", "auto") for b in brief.get("buildings", [])]
    shape_str = " + ".join(shapes) if shapes else "auto"
    source = brief.get("source", "fallback")
    text = label or f"Brief: {count}x [{shape_str}] ({source})"
    return graph.add_node(
        "brief",
        text,
        parent_id=parent_id,
        payload={"design_brief": brief},
    )


def make_clarify_node(
    graph: DecisionGraph,
    clarification_request: dict[str, Any],
    parent_id: str | None,
) -> str:
    """Node for an interactive clarification — the agent asking the user back.

    ``clarification_request`` is ``ClarificationRequest.to_dict()`` (a ``summary``
    plus a list of ``fields``, each with chip ``options``). The UI renders it as a
    form and POSTs answers to ``/sessions/{id}/clarify``.
    """
    fields = clarification_request.get("fields", []) if isinstance(clarification_request, dict) else []
    keys = ", ".join(f.get("key", "?") for f in fields)
    return graph.add_node(
        "clarify",
        f"Clarify: {keys}" if keys else "Clarification requested",
        parent_id=parent_id,
        payload={"clarification_request": clarification_request},
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
    """Create a branch node with one state-child per Pareto option.

    Returns the branch node id.  Children are all ``is_selected=False``
    until the user explicitly selects one.
    """
    branch_id = graph.add_node(
        "branch",
        f"Pareto alternatives ({len(pareto_solutions)} options)",
        parent_id=parent_id,
        payload={"option_count": len(pareto_solutions)},
        is_selected=False,   # branch itself is not a leaf — don't advance head
    )
    for opt in pareto_solutions:
        rank = opt.get("rank", "?")
        score = opt.get("combined_score", opt.get("avg_combined_score", 0.0))
        graph.add_node(
            "state",
            f"Option {rank} (score={score:.3f})",
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
            "label": b.get("label", f"Building {i+1}"),
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
