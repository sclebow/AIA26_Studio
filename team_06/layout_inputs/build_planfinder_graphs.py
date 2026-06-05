"""
Generate planfinder_graphs.json from Planfinder_Dataset/pf_jsons/ layouts.

Pipeline:
  1. create_graph_from_layout() — same as RPLAN, gives full node/edge attributes:
       nodes: name, program (raw: bed/bath/living/etc.), area, size, betweenness_centrality
       edges: edge_types (['access'] for doors, ['adjacency'] for shared walls)
  2. collapse_through_extra() — adds synthetic direct access edges between rooms
       that share a corridor/extra intermediary.
       WHY: PF layouts use a circulation corridor as the hub, so direct connections
       like bedroom→living room never appear as raw door edges. The collapse
       makes these reachable so PROGRAM_PAIRS features fire correctly in the
       graph embedder — matching RPLAN's direct-connection architecture.
       Betweenness centrality is NOT recalculated, so it still reflects the
       true corridor-based circulation pattern.

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

EXTRA_PROGRAMS = {"extra", "circulation", "storage", "fusebox"}


def is_empty_layout(layout: dict) -> bool:
    """Skip layouts that contain only extra/circulation rooms."""
    real_programs = {"bed", "bath", "living", "kitchen", "dining", "foyer"}
    rooms = layout.get("rooms", [])
    return not any(
        r.get("attributes", {}).get("program", "").lower() in real_programs
        for r in rooms
    )


def collapse_through_extra(G: nx.Graph) -> nx.Graph:
    """Add synthetic direct access edges between rooms that share a corridor.

    Planfinder rooms connect via a circulation/extra node, so pairs like
    bedroom→living room never appear as direct door edges. This adds them
    so the graph embedder's PROGRAM_PAIRS features can fire.

    Only adds access edges — adjacency edges from Shapely wall detection
    are left unchanged. Betweenness centrality is not recalculated.
    """
    extra_nodes = [
        n for n in G.nodes()
        if G.nodes[n].get("program", "").lower() in EXTRA_PROGRAMS
    ]
    for extra in extra_nodes:
        # Neighbours of this corridor that are real rooms (not other corridors)
        real_neighbours = [
            n for n in G.neighbors(extra)
            if G.nodes[n].get("program", "").lower() not in EXTRA_PROGRAMS
            and "access" in G[extra][n].get("edge_types", [])
        ]
        for i in range(len(real_neighbours)):
            for j in range(i + 1, len(real_neighbours)):
                r1, r2 = real_neighbours[i], real_neighbours[j]
                if G.has_edge(r1, r2):
                    edge_types = G[r1][r2].get("edge_types", [])
                    if "access" not in edge_types:
                        edge_types.append("access")
                    G[r1][r2]["edge_types"] = edge_types
                else:
                    G.add_edge(r1, r2, edge_types=["access"])
    return G


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
            G = collapse_through_extra(G)
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
