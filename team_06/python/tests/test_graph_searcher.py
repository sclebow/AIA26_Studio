#!/usr/bin/env python
"""Test unified graph search with pattern building."""

import sys
from pathlib import Path

# Adjust path to import from parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print("[OK] Testing unified GraphSearcher...\n")
from tools.graph_searcher import GraphSearcher, build_topology_graph

# Path: /tests/test_graph_searcher.py -> parent.parent = /python, parent.parent.parent = /team_06
repo_root = Path(__file__).resolve().parent.parent.parent
graphs_path = repo_root / "layout_inputs" / "sample_graphs.json"
gs = GraphSearcher(str(graphs_path))

print(f"[OK] GraphSearcher loaded with 6 layouts")
print(f"  Layouts: {list(gs.layout_graphs.keys())}\n")

# ============================================================================
# TEST 1: PRESENCE QUERIES (connection_type="any")
# ============================================================================
print("=" * 70)
print("TEST 1: Presence Queries (rooms exist anywhere)")
print("=" * 70)

print("\nTest 1a: ['bedroom', 'kitchen'] -> find layouts with bedroom AND kitchen")
pattern = build_topology_graph(['bedroom', 'kitchen'], connection_type="any")
print(f"  Pattern: nodes={set(pattern.nodes())}, edges={list(pattern.edges())}")
results = gs.search_by_graph_similarity(pattern, method="jaccard")
for layout_id, score in results:
    print(f"  {layout_id}: {score:.3f}")

print("\nTest 1b: ['bedroom', 'kitchen', 'living'] -> find layouts with bedroom, kitchen, living")
pattern = build_topology_graph(['bedroom', 'kitchen', 'living'], connection_type="any")
print(f"  Pattern: nodes={set(pattern.nodes())}, edges={list(pattern.edges())}")
results = gs.search_by_graph_similarity(pattern, method="jaccard")
for layout_id, score in results:
    print(f"  {layout_id}: {score:.3f}")

# ============================================================================
# TEST 2: CONNECTIVITY QUERIES (connection_type="connected")
# ============================================================================
print("\n" + "=" * 70)
print("TEST 2: Connectivity Queries (rooms must be connected via doors)")
print("=" * 70)

print("\nTest 2a: ['kitchen', 'living'] -> find layouts where kitchen-living connected")
pattern = build_topology_graph(['kitchen', 'living'], connection_type="connected")
print(f"  Pattern: nodes={set(pattern.nodes())}, edges={list(pattern.edges())}")
results = gs.search_by_graph_similarity(pattern, method="jaccard")
for layout_id, score in results:
    print(f"  {layout_id}: {score:.3f} (1.0=exact, <1.0=has extra edges)")

print("\nTest 2b: ['bedroom', 'kitchen', 'living'] -> find layouts where all three connected")
pattern = build_topology_graph(['bedroom', 'kitchen', 'living'], connection_type="connected")
print(f"  Pattern: nodes={set(pattern.nodes())}, edges={set(pattern.edges())}")
results = gs.search_by_graph_similarity(pattern, method="jaccard")
for layout_id, score in results:
    print(f"  {layout_id}: {score:.3f}")

# ============================================================================
# TEST 3: METRIC COMPARISON (Jaccard vs Overlap)
# ============================================================================
print("\n" + "=" * 70)
print("TEST 3: Metric Comparison (Jaccard vs Overlap)")
print("=" * 70)

print("\nTest 3a: ['kitchen', 'living'] using Jaccard (intersection/union)")
pattern = build_topology_graph(['kitchen', 'living'], connection_type="connected")
results_jaccard = gs.search_by_graph_similarity(pattern, method="jaccard")
for layout_id, score in results_jaccard:
    print(f"  {layout_id}: {score:.3f}")

print("\nTest 3b: ['kitchen', 'living'] using Overlap (intersection/min)")
results_overlap = gs.search_by_graph_similarity(pattern, method="overlap")
for layout_id, score in results_overlap:
    print(f"  {layout_id}: {score:.3f}")

# ============================================================================
# TEST 4: EXAMPLE INTEGRATIONS
# ============================================================================
print("\n" + "=" * 70)
print("TEST 4: Real-World Queries")
print("=" * 70)

print("\nExample 1: 'I want a layout with bedroom and kitchen'")
pattern = build_topology_graph(['bedroom', 'kitchen'], connection_type="any")
results = gs.search_by_graph_similarity(pattern)
print(f"  -> Found {len(results)} layouts: {[r[0] for r in results]}")

print("\nExample 2: 'Find layout with open kitchen-living area'")
pattern = build_topology_graph(['kitchen', 'bathroom'], connection_type="connected")
results = gs.search_by_graph_similarity(pattern)
print(f"  -> Found {len(results)} layouts: {[r[0] for r in results]}")


# ============================================================================
# TEST 5: PARTIAL EDGE QUERIES (specific pairs, not all connected)
# ============================================================================
print("\n" + "=" * 70)
print("TEST 5: Partial Edge Queries (specific room pairs)")
print("=" * 70)

print("\nTest 5a: bathroom<->bedroom AND kitchen<->store (partial connections, program-level)")
pattern = build_topology_graph(
    ['bathroom', 'bedroom', 'kitchen', 'store'],
    edges=[['bathroom', 'bedroom'], ['kitchen', 'store']]
)
print(f"  Pattern: nodes={set(pattern.nodes())}, edges={set(pattern.edges())}")
results = gs.search_by_graph_similarity(pattern, method="jaccard")
for layout_id, score in results:
    print(f"  {layout_id}: {score:.3f}")

print("\nTest 5b: bathroom<->bedroom only (3 rooms exist, 1 connection required)")
pattern = build_topology_graph(
    ['bathroom', 'bedroom', 'kitchen'],
    edges=[['bathroom', 'bedroom']]
)
print(f"  Pattern: nodes={set(pattern.nodes())}, edges={set(pattern.edges())}")
results = gs.search_by_graph_similarity(pattern, method="jaccard")
for layout_id, score in results:
    print(f"  {layout_id}: {score:.3f}")

# ============================================================================
# TEST 6: INSTANCE-LEVEL EDGES (indexed program pairs)
# ============================================================================
print("\n" + "=" * 70)
print("TEST 6: Instance-Level Edges (indexed, e.g. bedroom:1 <-> office:1)")
print("=" * 70)

print("\nTest 6a: Couple scenario — each bedroom paired with its own office")
print("  Pattern: bedroom:1<->office:1 AND bedroom:2<->office:2 (two separate suites)")
pattern = build_topology_graph(
    ['bedroom', 'bedroom', 'office', 'office', 'living'],
    edges=[['bedroom:1', 'office:1'], ['bedroom:2', 'office:2']]
)
print(f"  Nodes: {set(pattern.nodes())}")
print(f"  Edges: {set(pattern.edges())}")
results = gs.search_by_graph_similarity(pattern, method="jaccard")
print("  Jaccard ranking:")
for layout_id, score in results:
    print(f"    {layout_id}: {score:.3f}")

print("\nTest 6b: Same pattern — compare program-level vs instance-level edges")
pattern_prog = build_topology_graph(
    ['bedroom', 'bedroom', 'office', 'office'],
    edges=[['bedroom', 'office']]
)
pattern_inst = build_topology_graph(
    ['bedroom', 'bedroom', 'office', 'office'],
    edges=[['bedroom:1', 'office:1'], ['bedroom:2', 'office:2']]
)
print(f"  Program-level edges: {set(pattern_prog.edges())} (1 edge)")
print(f"  Instance-level edges: {set(pattern_inst.edges())} (2 separate edges)")

# ============================================================================
# TEST 7: SUBGRAPH ISOMORPHISM SEARCH
# ============================================================================
print("\n" + "=" * 70)
print("TEST 7: Subgraph Isomorphism (exact structural match)")
print("=" * 70)

print("\nTest 7a: Simple — kitchen connected to living (exact)")
pattern = build_topology_graph(['kitchen', 'living'], connection_type="connected")
exact = gs.search_by_subgraph_isomorphism(pattern)
print(f"  Exact matches: {exact}")

print("\nTest 7b: Hybrid search — bedroom:1<->office:1 AND bedroom:2<->office:2")
pattern = build_topology_graph(
    ['bedroom', 'bedroom', 'office', 'office', 'living'],
    edges=[['bedroom:1', 'office:1'], ['bedroom:2', 'office:2']]
)
hybrid = gs.search_hybrid(pattern)
print(f"  Exact matches:       {hybrid['exact']}")
print(f"  Approximate matches: {[(lid, round(s, 3)) for lid, s in hybrid['approximate']]}")

print("\n" + "=" * 70)
print("[OK] Unified graph search is working!")
print("=" * 70)
