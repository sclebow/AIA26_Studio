"""
TOPOLOGIC_ANALYSIS — real door-adjacency graph + degree metrics.
Fixed: returns structured graph_data for frontend Cytoscape/D3 rendering.
"""

from __future__ import annotations
from nodes.editing import _edits

try:
    import topologic  # noqa: F401
    _TOPOLOGIC_AVAILABLE = True
except Exception:
    _TOPOLOGIC_AVAILABLE = False


def build_topologic_analysis_node():
    def topologic_analysis_node(state: dict) -> dict:
        layout = _edits.load(state.get("layout_json_string", ""))
        if layout is None:
            return {**state, "adjacency_graph": {}, "graph_data": {"nodes": [], "edges": []}}

        rooms      = layout.get("rooms", [])
        room_by_id = {r.get("id", ""): r for r in rooms}
        room_names = {r.get("id", ""): r.get("name", "unknown") for r in rooms}

        # Build adjacency from door connectsRooms
        adj: dict = {}
        edges = []
        for door in layout.get("doors", []):
            conn = door.get("attributes", {}).get("connectsRooms", [])
            if len(conn) == 2:
                a, b = conn
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
                edges.append({
                    "source":  a,
                    "target":  b,
                    "door_id": door.get("id", ""),
                    "door_name": door.get("name", ""),
                })

        # Named adjacency dict (for text response)
        named: dict = {}
        for rid, neighbours in adj.items():
            named[room_names.get(rid, rid)] = sorted(room_names.get(n, n) for n in neighbours)

        # Degree metrics
        degrees = {rid: len(nbrs) for rid, nbrs in adj.items()}
        most_connected_id = max(degrees, key=degrees.get) if degrees else None
        isolated_ids = [r.get("id") for r in rooms if r.get("id") not in adj]

        metrics = {
            "most_connected":       room_names.get(most_connected_id, "none"),
            "most_connected_degree": degrees.get(most_connected_id, 0),
            "isolated_rooms":       [room_names.get(rid, rid) for rid in isolated_ids],
            "topologicpy_available": _TOPOLOGIC_AVAILABLE,
        }

        # Structured graph_data for frontend
        nodes = []
        for room in rooms:
            rid   = room.get("id", "")
            rtype = room.get("attributes", {}).get("roomType", "living")
            nodes.append({
                "id":        rid,
                "name":      room.get("name", "?"),
                "room_type": rtype,
                "degree":    degrees.get(rid, 0),
                "isolated":  rid in isolated_ids,
            })

        graph_data = {
            "nodes":   nodes,
            "edges":   edges,
            "metrics": metrics,
        }

        print(f"[topologic_analysis] {len(nodes)} rooms, {len(edges)} connections | most_connected={metrics['most_connected']}")
        return {**state, "adjacency_graph": named, "graph_data": graph_data}

    return topologic_analysis_node
