"""
TOPOLOGIC_ANALYSIS placeholder — builds room adjacency graph from door connections.
TODO: Wire to TopologicPy or MCP compute_topologic_adjacency tool.
"""

from __future__ import annotations
import json


def build_topologic_analysis_node():
    """Return the topologic_analysis node function."""

    def topologic_analysis_node(state: dict) -> dict:
        layout_json_string: str = state.get("layout_json_string", "")

        print("[topologic_analysis] PLACEHOLDER — building mock adjacency graph from doors")

        adjacency_graph: dict = {}

        # Mock: parse door connections from layout JSON
        try:
            layout = json.loads(layout_json_string)
            rooms = {r.get("id", ""): r.get("name", "unknown") for r in layout.get("rooms", [])}

            # Build adjacency from door connectsRooms pairs
            for door in layout.get("doors", []):
                connects = door.get("connectsRooms", [])
                if len(connects) == 2:
                    a, b = connects[0], connects[1]
                    adjacency_graph.setdefault(a, [])
                    adjacency_graph.setdefault(b, [])
                    if b not in adjacency_graph[a]:
                        adjacency_graph[a].append(b)
                    if a not in adjacency_graph[b]:
                        adjacency_graph[b].append(a)

            # Annotate with room names for readability
            named_graph: dict = {}
            for room_id, neighbours in adjacency_graph.items():
                room_name = rooms.get(room_id, room_id)
                named_graph[room_name] = [rooms.get(n, n) for n in neighbours]

            adjacency_graph = named_graph
            print(f"[topologic_analysis] Adjacency graph: {adjacency_graph}")
        except Exception as exc:
            print(f"[topologic_analysis] Parse error ({exc}) — empty graph")
            adjacency_graph = {"_error": str(exc)}

        return {
            **state,
            "adjacency_graph": adjacency_graph,
        }

    return topologic_analysis_node
