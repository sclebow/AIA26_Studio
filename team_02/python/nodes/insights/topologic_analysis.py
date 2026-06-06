"""
TOPOLOGIC_ANALYSIS — real door-adjacency graph + NetworkX metrics.

Builds the ROOM graph (rooms = nodes, doors = edges) and computes graph-theoretic
metrics with NetworkX (previously hand-rolled): degree + betweenness centrality,
articulation points (rooms whose removal splits the plan), connected components
(detached zones), and isolation. Edges are tagged with the TRANSMISSIVE-sense
conflicts that bleed across them (acoustic / olfactory / thermal), using the live
comfort scores when available — this is the "good vs bad connection" data the
room-topology view renders. graph_data shape is consumed by the frontend overlay.
"""

from __future__ import annotations
import json
from nodes.editing import _edits

try:
    from comfort.sense_model import TRANSMISSIVE
except ImportError:  # same-dir fallback
    TRANSMISSIVE = ["acoustic", "olfactory", "thermal"]

try:
    import networkx as nx
    _NX_AVAILABLE = True
except Exception:
    _NX_AVAILABLE = False


def _parse(s):
    try:
        return json.loads(s) if s else None
    except Exception:
        return None


def build_topologic_analysis_node():
    def topologic_analysis_node(state: dict) -> dict:
        layout = _edits.load(state.get("layout_json_string", ""))
        if layout is None:
            return {**state, "adjacency_graph": {}, "graph_data": {"nodes": [], "edges": []}}

        rooms      = layout.get("rooms", [])
        room_names = {r.get("id", ""): r.get("name", "unknown") for r in rooms}
        rtype      = {r.get("id"): r.get("attributes", {}).get("roomType", "living") for r in rooms}

        # Transmissive-sense failures per room (for edge tagging), from live scores.
        scores = _parse(state.get("last_scores_json", "")) or {}
        fail_by_id = {}
        for r in scores.get("rooms", []):
            cs = r.get("comfortScores", {})
            fail_by_id[r.get("roomId")] = {s for s in TRANSMISSIVE if (cs.get(s, 1.0) or 0) < 0.5}

        # Door adjacency → edges
        edges = []
        adj_pairs = []
        for door in layout.get("doors", []):
            conn = door.get("attributes", {}).get("connectsRooms", [])
            if len(conn) == 2:
                a, b = conn
                adj_pairs.append((a, b))
                conflicts = sorted({s for s in TRANSMISSIVE
                                    if s in fail_by_id.get(a, set()) or s in fail_by_id.get(b, set())})
                edges.append({
                    "source": a, "target": b,
                    "door_id": door.get("id", ""), "door_name": door.get("name", ""),
                    "transmissive_conflicts": conflicts,   # senses bleeding across this door
                    "healthy": not conflicts,
                })

        # ── Graph metrics via NetworkX ──
        G = None
        degree = betweenness = {}
        articulation = set()
        components = []
        if _NX_AVAILABLE:
            G = nx.Graph()
            G.add_nodes_from(r.get("id", "") for r in rooms)
            G.add_edges_from(adj_pairs)
            degree = dict(G.degree())
            betweenness = nx.betweenness_centrality(G) if G.number_of_nodes() > 2 else {n: 0.0 for n in G}
            articulation = set(nx.articulation_points(G)) if G.number_of_edges() else set()
            components = [sorted(room_names.get(n, n) for n in c) for c in nx.connected_components(G)]
        else:  # fallback: degree only
            adj = {}
            for a, b in adj_pairs:
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
            degree = {r.get("id", ""): len(adj.get(r.get("id", ""), set())) for r in rooms}

        isolated_ids = [r.get("id") for r in rooms if degree.get(r.get("id"), 0) == 0]
        most_connected_id = max(degree, key=degree.get) if degree else None

        nodes = []
        for room in rooms:
            rid = room.get("id", "")
            nodes.append({
                "id":          rid,
                "name":        room.get("name", "?"),
                "room_type":   rtype.get(rid, "living"),
                "degree":      degree.get(rid, 0),
                "betweenness": round(betweenness.get(rid, 0.0), 3),
                "isolated":    rid in isolated_ids,
                "is_bridge":   rid in articulation,   # removal would split the plan
            })

        metrics = {
            "most_connected":        room_names.get(most_connected_id, "none"),
            "most_connected_degree": degree.get(most_connected_id, 0),
            "isolated_rooms":        [room_names.get(rid, rid) for rid in isolated_ids],
            "bridge_rooms":          sorted(room_names.get(rid, rid) for rid in articulation),
            "num_components":        len(components) if components else (1 if rooms else 0),
            "components":            components,
            "networkx_available":    _NX_AVAILABLE,
        }

        named = {}
        for a, b in adj_pairs:
            named.setdefault(room_names.get(a, a), []).append(room_names.get(b, b))
            named.setdefault(room_names.get(b, b), []).append(room_names.get(a, a))
        named = {k: sorted(set(v)) for k, v in named.items()}

        graph_data = {"nodes": nodes, "edges": edges, "metrics": metrics}
        print(f"[topologic_analysis] nx={_NX_AVAILABLE} | {len(nodes)} rooms, {len(edges)} doors "
              f"| hub={metrics['most_connected']} bridges={metrics['bridge_rooms']} comps={metrics['num_components']}")
        return {**state, "adjacency_graph": named, "graph_data": graph_data}

    return topologic_analysis_node
