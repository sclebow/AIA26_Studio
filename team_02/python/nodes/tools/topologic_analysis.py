"""
TOPOLOGIC_ANALYSIS — real room-adjacency graph from door connections, plus degree
metrics. Pure Python (no Rhino). If topologicpy is installed it is detected and
noted, but the authoritative adjacency here is the door graph; building a
topologicpy CellComplex from room polygons is a future improvement (flagged).
"""

from __future__ import annotations
from nodes.tools import _edits

try:
    import topologic  # noqa: F401  (topologicpy exposes the `topologic` module)
    _TOPOLOGIC_AVAILABLE = True
except Exception:
    _TOPOLOGIC_AVAILABLE = False


def build_topologic_analysis_node():
    def topologic_analysis_node(state: dict) -> dict:
        layout = _edits.load(state.get("layout_json_string", ""))
        if layout is None:
            return {**state, "adjacency_graph": {"_error": "no layout"}}

        rooms = {r.get("id", ""): r.get("name", "unknown") for r in layout.get("rooms", [])}

        # Adjacency from door connectsRooms pairs (under attributes — the real schema).
        adj: dict = {}
        for door in layout.get("doors", []):
            conn = door.get("attributes", {}).get("connectsRooms", [])
            if len(conn) == 2:
                a, b = conn
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)

        named: dict = {}
        for rid, neighbours in adj.items():
            named[rooms.get(rid, rid)] = sorted(rooms.get(n, n) for n in neighbours)

        # Degree metrics
        degrees = {name: len(neis) for name, neis in named.items()}
        most_connected = max(degrees, key=degrees.get) if degrees else None
        isolated = [rooms.get(rid, rid) for rid in rooms if rid not in adj]

        metrics = {
            "degrees": degrees,
            "most_connected": most_connected,
            "isolated_rooms": isolated,
            "topologicpy_available": _TOPOLOGIC_AVAILABLE,
        }
        print("[topologic_analysis] graph={} | most_connected={} | topologicpy={}".format(
            named, most_connected, _TOPOLOGIC_AVAILABLE))

        return {**state, "adjacency_graph": named, "adjacency_metrics": metrics}

    return topologic_analysis_node
