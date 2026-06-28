"""Decision-graph runtime — design-evolution DAG (branches, selections, backtrack).

Thin wrapper over the EXISTING graph implementation, which is the source of truth:

    connection.decision_graph.DecisionGraph
    connection.decision_graph.make_intent_node / make_action_node /
                              make_branch_nodes / make_state_node

No graph logic is reimplemented. The notebook (test_decision_graph.ipynb) and the
frontend decision tree both build/serialize graphs through these helpers and get
the identical {nodes, edges, head} payload a DAG renderer consumes.
"""
from __future__ import annotations

from typing import Any

from ..decision_graph import (
    DecisionGraph,
    make_action_node,
    make_branch_nodes,
    make_intent_node,
    make_state_node,
)


def new_graph() -> DecisionGraph:
    return DecisionGraph()


def from_payload(data: dict[str, Any]) -> DecisionGraph:
    """Rebuild a graph from a previously serialized {nodes, edges, head} payload."""
    return DecisionGraph.from_dict(data)


def add_intent(graph: DecisionGraph, message: str) -> str:
    return make_intent_node(graph, message)


def add_action(graph: DecisionGraph, tool_name: str, input_preview: str = "", parent_id: str | None = None) -> str:
    return make_action_node(graph, tool_name, input_preview, parent_id or graph.current_head())


def branch_options(graph: DecisionGraph, options: list[dict[str, Any]], parent_id: str | None = None) -> str:
    """Add a branch node with one child per Pareto/candidate option. Returns the
    branch node id; children are unselected until select_path picks one."""
    return make_branch_nodes(graph, parent_id or graph.current_head(), options)


def add_state(graph: DecisionGraph, placed_buildings: list[dict[str, Any]], parent_id: str | None = None) -> str:
    return make_state_node(graph, parent_id or graph.current_head(), placed_buildings)


def select_path(graph: DecisionGraph, node_id: str) -> bool:
    """Select a node (deselects sibling options) and move the head to it."""
    return graph.select_node(node_id)


def backtrack(graph: DecisionGraph, node_id: str) -> bool:
    """Re-select an earlier node to continue the design from that point."""
    return graph.select_node(node_id)


def to_frontend_payload(graph: DecisionGraph) -> dict[str, Any]:
    """{nodes, edges, head} — directly consumable by the frontend DAG renderer."""
    return graph.to_dict()
