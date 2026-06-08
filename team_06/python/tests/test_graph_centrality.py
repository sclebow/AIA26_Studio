"""
Diagnostic: betweenness centrality on RPLAN vs Planfinder graphs.

Checks:
  1. Which program type is the circulation hub in each dataset
  2. How many layouts have all-zero centrality (disconnected access graph)
  3. Which PROGRAM_PAIRS access features are reachable in each dataset
  4. Sample layout breakdown for visual inspection

Run from repo root:
  .venv/Scripts/python.exe team_06/python/tests/test_graph_centrality.py
"""

import json
import sys
import networkx as nx
from pathlib import Path
from collections import defaultdict

REPO_ROOT  = Path(__file__).resolve().parents[3]
TEAM_ROOT  = REPO_ROOT / "team_06"
sys.path.insert(0, str(TEAM_ROOT / "python"))

from utils.graph_embedder import normalize_program, PROGRAMS, PROGRAM_PAIRS

SAMPLE_GRAPHS_PATH     = TEAM_ROOT / "layout_inputs" / "sample_graphs.json"
RPLAN_GRAPHS_PATH      = TEAM_ROOT / "layout_inputs" / "RPLAN_Dataset_R-NB" / "graphs.json"
PF_GRAPHS_PATH         = TEAM_ROOT / "layout_inputs" / "planfinder_graphs.json"

SEP = "=" * 72


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_graphs(path: Path) -> dict[str, nx.Graph]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {lid: nx.node_link_graph(data) for lid, data in raw.items()}


def access_subgraph(G: nx.Graph) -> nx.Graph:
    return nx.Graph([
        (u, v) for u, v, d in G.edges(data=True)
        if "access" in d.get("edge_types", [])
    ])


def centrality_by_program(G: nx.Graph) -> dict[str, float]:
    """Average betweenness centrality per canonical program type."""
    bc = G.nodes[list(G.nodes())[0]].get("betweenness_centrality", None)
    if bc is None:
        # Recompute if not stored (e.g. old RPLAN graphs)
        ag = access_subgraph(G)
        bc_map = nx.betweenness_centrality(ag) if ag.number_of_nodes() > 0 else {}
    else:
        bc_map = {n: G.nodes[n].get("betweenness_centrality", 0.0) for n in G.nodes()}

    by_prog = defaultdict(list)
    for n in G.nodes():
        prog = normalize_program(G.nodes[n].get("program", ""))
        by_prog[prog].append(bc_map.get(n, 0.0))

    return {p: round(sum(v) / len(v), 3) for p, v in by_prog.items()}


def access_pairs_present(G: nx.Graph) -> set[tuple]:
    """Which PROGRAM_PAIRS have at least one access edge in this layout."""
    ag = access_subgraph(G)
    found = set()
    for u, v in ag.edges():
        pu = normalize_program(G.nodes[u].get("program", ""))
        pv = normalize_program(G.nodes[v].get("program", ""))
        found.add(tuple(sorted([pu, pv])))
    return found


# ---------------------------------------------------------------------------
# Section 1 — per-layout BC breakdown (sample layouts only, always readable)
# ---------------------------------------------------------------------------

def section_per_layout(graphs: dict, label: str, limit: int = 8):
    print(f"\n{SEP}")
    print(f"[1] PER-LAYOUT CENTRALITY — {label} (first {limit})")
    print(SEP)
    for lid, G in list(graphs.items())[:limit]:
        cbp = centrality_by_program(G)
        # Show only programs present
        present = {p: v for p, v in cbp.items() if v > 0}
        hub = max(cbp, key=cbp.get) if cbp else "—"
        print(f"  {lid}")
        print(f"    hub: {hub}   |   centrality: {present}")


# ---------------------------------------------------------------------------
# Section 2 — dataset-wide: which program type is most often the hub
# ---------------------------------------------------------------------------

def section_hub_distribution(graphs: dict, label: str):
    print(f"\n{SEP}")
    print(f"[2] HUB DISTRIBUTION — {label} ({len(graphs)} layouts)")
    print(SEP)

    hub_counts = defaultdict(int)
    all_zero   = 0

    for G in graphs.values():
        cbp = centrality_by_program(G)
        total_bc = sum(cbp.values())
        if total_bc == 0:
            all_zero += 1
            hub_counts["(all zero — disconnected)"] += 1
        else:
            hub = max(cbp, key=cbp.get)
            hub_counts[hub] += 1

    for prog, count in sorted(hub_counts.items(), key=lambda x: -x[1]):
        pct = 100 * count / len(graphs)
        bar = "#" * int(pct / 2)
        print(f"  {prog:<20} {count:>4} layouts  ({pct:5.1f}%)  {bar}")

    if all_zero:
        print(f"\n  WARNING: {all_zero} layouts have all-zero centrality (access graph disconnected)")


# ---------------------------------------------------------------------------
# Section 3 — access pair coverage across the whole dataset
# ---------------------------------------------------------------------------

def section_pair_coverage(graphs: dict, label: str):
    print(f"\n{SEP}")
    print(f"[3] ACCESS PAIR COVERAGE — {label} ({len(graphs)} layouts)")
    print(SEP)
    print(f"  (how many layouts have at least one door between each program pair)")
    print()

    pair_counts = defaultdict(int)
    for G in graphs.values():
        for pair in access_pairs_present(G):
            pair_counts[pair] += 1

    total = len(graphs)
    # Normalise PROGRAM_PAIRS to sorted tuples for lookup (same as pair_counts keys)
    sorted_program_pairs = {tuple(sorted(p)) for p in PROGRAM_PAIRS}

    for pair in PROGRAM_PAIRS:
        key   = tuple(sorted(pair))
        count = pair_counts.get(key, 0)
        pct   = 100 * count / total
        bar   = "#" * int(pct / 2)
        flag  = "  <-- NEVER" if count == 0 else ""
        print(f"  {str(pair):<40} {count:>4} / {total}  ({pct:5.1f}%)  {bar}{flag}")

    # Show pairs found in data but not covered by PROGRAM_PAIRS
    extra_pairs = {p for p in pair_counts if p not in sorted_program_pairs}
    if extra_pairs:
        print(f"\n  Pairs in data but NOT in PROGRAM_PAIRS (invisible to embedder):")
        for pair in sorted(extra_pairs):
            count = pair_counts[pair]
            pct   = 100 * count / total
            print(f"  {str(pair):<40} {count:>4} / {total}  ({pct:5.1f}%)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\nLoading graphs...")
    sample_graphs = load_graphs(SAMPLE_GRAPHS_PATH)
    pf_graphs     = load_graphs(PF_GRAPHS_PATH)
    print(f"  RPLAN sample:  {len(sample_graphs)} layouts")
    print(f"  Planfinder:    {len(pf_graphs)} layouts")

    # --- RPLAN sample (all 6, always visible) ---
    section_per_layout(sample_graphs, "RPLAN sample_graphs", limit=6)
    section_hub_distribution(sample_graphs, "RPLAN sample_graphs")
    section_pair_coverage(sample_graphs, "RPLAN sample_graphs")

    # --- Planfinder ---
    section_per_layout(pf_graphs, "Planfinder", limit=8)
    section_hub_distribution(pf_graphs, "Planfinder")
    section_pair_coverage(pf_graphs, "Planfinder")

    print(f"\n{SEP}")
    print("Done.")


if __name__ == "__main__":
    main()
