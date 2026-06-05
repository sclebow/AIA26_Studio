"""
Generate planfinder_graphs.json from Planfinder_Dataset/pf_jsons/ layouts.

Uses the same schema_to_graph.create_graph_from_layout() pipeline as RPLAN so
the resulting graphs have identical node/edge attributes:
  - nodes: name, program (raw: bed/bath/living/etc.), area, size, betweenness_centrality
  - edges: edge_types (['access'] for doors, ['adjacency'] for shared walls), weight

Run from repo root with venv active:
    .venv/Scripts/python.exe team_06/layout_inputs/build_planfinder_graphs.py
"""

import json
import sys
import networkx as nx
from pathlib import Path

REPO_ROOT      = Path(__file__).resolve().parents[2]
PLANFINDER_DIR = Path(__file__).resolve().parent / "Planfinder_Dataset" / "pf_jsons"
OUTPUT_PATH    = Path(__file__).resolve().parent / "planfinder_graphs.json"

sys.path.insert(0, str(REPO_ROOT / "team_06" / "python"))
from utils.parser.schema_to_graph import create_graph_from_layout


def is_empty_layout(layout: dict) -> bool:
    """Skip layouts that contain only extra/circulation rooms."""
    real_programs = {"bed", "bath", "living", "kitchen", "dining", "foyer"}
    rooms = layout.get("rooms", [])
    return not any(
        r.get("attributes", {}).get("program", "").lower() in real_programs
        for r in rooms
    )


def main():
    json_files = sorted(PLANFINDER_DIR.glob("*.json"))
    print(f"Found {len(json_files)} layout files in {PLANFINDER_DIR.name}")

    graphs  = {}
    skipped = 0
    errors  = 0

    for json_file in json_files:
        layout_id = json_file.stem
        layout    = json.loads(json_file.read_text(encoding="utf-8"))

        if not layout.get("rooms") or not layout.get("doors"):
            print(f"  skip (no rooms/doors): {layout_id}")
            skipped += 1
            continue

        if is_empty_layout(layout):
            print(f"  skip (empty):          {layout_id}")
            skipped += 1
            continue

        try:
            G = create_graph_from_layout(layout)
            graphs[layout_id] = nx.node_link_data(G)
            print(f"  + {layout_id}  ({G.number_of_nodes()} rooms, {G.number_of_edges()} edges)")
        except Exception as e:
            print(f"  ERR {layout_id}: {e}")
            errors += 1

    OUTPUT_PATH.write_text(json.dumps(graphs, indent=2), encoding="utf-8")
    print(f"\nSaved {len(graphs)} graphs -> {OUTPUT_PATH}")
    print(f"Skipped: {skipped}  |  Errors: {errors}")


if __name__ == "__main__":
    main()
