"""
Generate planfinder_graphs.json from Planfinder_Dataset/ layouts.
Run from repo root with venv active:
    python team_06/layout_inputs/build_planfinder_graphs.py
"""

import json
import networkx as nx
from pathlib import Path

PLANFINDER_DIR = Path(__file__).resolve().parent / "Planfinder_Dataset"
OUTPUT_PATH    = Path(__file__).resolve().parent / "planfinder_graphs.json"

# Normalize Planfinder program names to match agent vocabulary
PROGRAM_MAP = {
    "bed":         "bedroom",
    "bath":        "bathroom",
    "wc":          "bathroom",
    "living":      "living",
    "kitchen":     "kitchen",
    "circulation": "extra",
    "storage":     "extra",
    "fusebox":     "extra",
}


def build_graph(layout: dict) -> nx.Graph:
    G = nx.Graph()
    for room in layout["rooms"]:
        room_id  = room["id"]
        raw_prog = room.get("attributes", {}).get("program", "") or room.get("program", "")
        program  = PROGRAM_MAP.get(raw_prog.lower(), raw_prog.lower())
        name     = room.get("name", "")
        G.add_node(room_id, name=name, program=program)

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


def main():
    graphs  = {}
    skipped = 0

    for json_file in sorted(PLANFINDER_DIR.glob("*.json")):
        layout    = json.loads(json_file.read_text(encoding="utf-8"))
        layout_id = layout.get("layoutId", json_file.stem)

        if not layout.get("rooms") or not layout.get("doors"):
            print(f"  skip (empty): {layout_id}")
            skipped += 1
            continue

        G = build_graph(layout)
        graphs[layout_id] = nx.node_link_data(G)
        print(f"  + {layout_id}")

    OUTPUT_PATH.write_text(json.dumps(graphs, indent=2), encoding="utf-8")
    print(f"\nSaved {len(graphs)} graphs -> {OUTPUT_PATH}  (skipped {skipped})")


if __name__ == "__main__":
    main()
