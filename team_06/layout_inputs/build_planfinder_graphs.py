"""
Generate planfinder_graphs.json from Planfinder_Dataset/pf_jsons/ layouts.

Reads the RPLAN-compatible JSONs (attributes.program field).
Applies two-hop edge collapse: rooms connected through a corridor/extra node
get a direct edge added between them, so Jaccard similarity works the same
way as for RPLAN layouts.

Run from repo root with venv active:
    python team_06/layout_inputs/build_planfinder_graphs.py
"""

import json
import networkx as nx
from pathlib import Path

PLANFINDER_DIR = Path(__file__).resolve().parent / "Planfinder_Dataset" / "pf_jsons"
OUTPUT_PATH    = Path(__file__).resolve().parent / "planfinder_graphs.json"

# Normalize program names to match agent/topology vocabulary
PROGRAM_MAP = {
    "bed":         "bedroom",
    "bath":        "bathroom",
    "wc":          "bathroom",
    "living":      "living",
    "kitchen":     "kitchen",
    "extra":       "extra",
    "circulation": "extra",
    "storage":     "extra",
    "fusebox":     "extra",
}


def build_graph(layout: dict) -> nx.Graph:
    G = nx.Graph()
    for room in layout["rooms"]:
        room_id  = room["id"]
        raw_prog = room.get("attributes", {}).get("program", "") or room.get("type", "")
        program  = PROGRAM_MAP.get(raw_prog.lower(), raw_prog.lower())
        G.add_node(room_id, name=room.get("name", ""), program=program)

    for door in layout["doors"]:
        connected = door["attributes"]["connectsRooms"]
        for i in range(len(connected)):
            for j in range(i + 1, len(connected)):
                r1, r2 = connected[i], connected[j]
                if G.has_edge(r1, r2):
                    G[r1][r2]["weight"] = G[r1][r2].get("weight", 1) + 1
                else:
                    G.add_edge(r1, r2, weight=1)

    return G


def collapse_through_extra(G: nx.Graph) -> nx.Graph:
    """Add direct edges between program rooms that share a corridor/extra intermediary.

    Planfinder rooms connect via a circulation corridor (extra node), so there
    are no direct bedroom-to-bathroom edges. This collapses those two-hop paths
    into direct edges so Jaccard similarity finds them.
    """
    extra_nodes = [n for n in G.nodes() if G.nodes[n].get("program") == "extra"]

    for extra_node in extra_nodes:
        program_neighbors = [
            n for n in G.neighbors(extra_node)
            if G.nodes[n].get("program") != "extra"
        ]
        for i in range(len(program_neighbors)):
            for j in range(i + 1, len(program_neighbors)):
                r1, r2 = program_neighbors[i], program_neighbors[j]
                if not G.has_edge(r1, r2):
                    G.add_edge(r1, r2, weight=1)

    return G


def main():
    graphs  = {}
    skipped = 0

    for json_file in sorted(PLANFINDER_DIR.glob("*.json")):
        layout    = json.loads(json_file.read_text(encoding="utf-8"))
        layout_id = json_file.stem

        rooms = layout.get("rooms", [])
        real_rooms = [
            r for r in rooms
            if PROGRAM_MAP.get(
                r.get("attributes", {}).get("program", "").lower(), ""
            ) != "extra"
        ]

        if not real_rooms or not layout.get("doors"):
            print(f"  skip (empty): {layout_id}")
            skipped += 1
            continue

        G = build_graph(layout)
        G = collapse_through_extra(G)
        graphs[layout_id] = nx.node_link_data(G)
        print(f"  + {layout_id}")

    OUTPUT_PATH.write_text(json.dumps(graphs, indent=2), encoding="utf-8")
    print(f"\nSaved {len(graphs)} graphs -> {OUTPUT_PATH}  (skipped {skipped})")


if __name__ == "__main__":
    main()
