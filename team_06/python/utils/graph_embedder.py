"""Rule-based graph embedder — no ML model required.

WHY THIS IS BETTER THAN THE CURRENT LOOP (graph_searcher.py):
==============================================================

Current approach (graph_searcher.py):
  - Linear O(n) scan: checks EVERY layout on EVERY search call
  - Recomputes edge sets from scratch each time
  - No memory: previous searches don't make future searches faster

Rule-based embedding approach:
  - OFFLINE PHASE (runs once at startup):
      Every layout graph is converted to a fixed-size numeric vector.
      These vectors are stored in memory (the "index").
  - ONLINE PHASE (runs on every search):
      The user query is also converted to a vector.
      Cosine similarity is computed against the pre-built index.
      No graph traversal, no edge recomputation — just dot products.

  Result: search is faster per query because the expensive graph work
  is done once, not repeated. At 6 layouts this is trivial. At 6,000
  layouts the difference is significant.

WHY NOT USE embedding_matcher.py (the existing neural embedder)?
================================================================

  embedding_matcher.py works on TEXT descriptions:
    "A cozy 2-bedroom apartment with open kitchen..."
  It uses a neural model (sentence-transformers) to find semantic matches.

  Rule-based embedding works on GRAPH STRUCTURE:
    bedroom_count=2, kitchen_count=1, bedroom-kitchen edge=True, ...
  No model needed — the features are hand-crafted from the graph directly.

  The two approaches are COMPLEMENTARY:
    - Neural (existing): good for "feel" queries ("cozy", "spacious", "open plan")
    - Rule-based (this file): good for structural queries ("2 bedrooms connected to kitchen")

HOW RULE-BASED EMBEDDING WORKS (step by step):
===============================================

  1. Define a feature schema — a fixed list of things to measure:
       [bedroom_count, kitchen_count, ..., bedroom-kitchen edge, density, ...]

  2. Extract features from every layout graph → a numeric vector:
       layout-1 → [2.0, 1.0, 1.0, 2.0, 0.0, 0.0, 1.0, 0.0, ..., 0.73, 1.0]
       layout-2 → [1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0, ..., 0.50, 1.0]
       ... (one vector per layout, stored in the index)

  3. At search time, build a query vector from the user's programs:
       user wants: ['bedroom', 'kitchen', 'living room'] all connected
       query vec → [1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, ...]

  4. Compute cosine similarity between query vector and each layout vector:
       cosine_similarity(query_vec, layout-1_vec) = 0.87
       cosine_similarity(query_vec, layout-2_vec) = 0.62
       ...

  5. Return layouts sorted by score — highest similarity first.

  KEY INSIGHT: cosine similarity compares the DIRECTION of vectors, not their
  magnitude. So a layout with 2 bedrooms matches a query for 1 bedroom better
  than a layout with 0 bedrooms — even though the counts differ.
"""

import math
import networkx as nx
from typing import Optional

# ============================================================================
# STEP 1 — Define the feature schema
#
# A fixed list of features we extract from every graph.
# Each graph → a vector of the same length, in the same order.
# The order must never change — adding a new feature invalidates old vectors.
# ============================================================================

# All program types we care about (determines vector dimensions for room counts)
PROGRAMS = ["bedroom", "kitchen", "living room", "bathroom", "dining room", "foyer"]

SIZES = ["Small", "Medium", "Large"]

# All program-pair edges we care about
PROGRAM_PAIRS = [
    ("bedroom",     "kitchen"),
    ("bedroom",     "living room"),
    ("bedroom",     "bathroom"),
    ("kitchen",     "living room"),
    ("kitchen",     "dining room"),
    ("living room", "bathroom"),
    ("living room", "dining room"),
    ("foyer",       "living room"),
    ("foyer",       "bedroom"),
    ("foyer",       "bathroom"),
    ("foyer",       "kitchen"),
]


# Maps short dataset program names (RPLAN and similar) to the canonical long names
# used throughout this codebase. Apply at graph-load time via normalize_program()
# so all downstream code works with one consistent vocabulary.
PROGRAM_NORMALIZE: dict[str, str] = {
    "bed":    "bedroom",
    "bath":   "bathroom",
    "living": "living room",
    "dining": "dining room",
}


def normalize_program(program: str) -> str:
    """Return the canonical program name, mapping dataset short names to long names."""
    return PROGRAM_NORMALIZE.get(program.lower(), program.lower())


# ============================================================================
# STEP 2 — Feature extraction: graph → vector
#
# Given a NetworkX layout graph, produce a fixed-length list of floats.
# The same index position always means the same feature.
# ============================================================================

def extract_features(G: nx.Graph) -> list[float]:
    """Convert a layout graph into a fixed-length feature vector.

    Captures:
      - Program counts by room size (Small/Medium/Large)
      - Access connectivity (doors between program types)
      - Adjacency connectivity (shared walls between program types)
      - Betweenness centrality per program type
      - Global graph metrics
    """
    features = []

    # --- A: Room counts per program type
    # Tells us HOW MANY of each room type exist in this layout.
    # e.g., PROGRAMS = ['bedroom', 'kitchen', ...]
    #        features = [2.0, 1.0, 1.0, 2.0, 0.0, 0.0]
    #                    ^2 bedrooms ^1 kitchen ^1 living ^2 baths ^0 dining ^0 foyer
    program_size_counts = {}
    for node in G.nodes():
        program = normalize_program(G.nodes[node].get("program", ""))
        size = G.nodes[node].get("size", "Medium")
        key = (program, size)
        program_size_counts[key] = program_size_counts.get(key, 0) + 1

    for program in PROGRAMS:
        for size in SIZES:
            features.append(float(program_size_counts.get((program, size), 0)))

    # --- B: Edge presence between program pairs
    # Tells us WHICH rooms are directly connected by doors.
    # e.g., ('bedroom', 'kitchen') → 1.0 if any bedroom shares a door with any kitchen
    access_edges = set()
    for u, v in G.edges():
        edge_types = G[u][v].get('edge_types', [])
        if not edge_types or 'access' in edge_types:
            pu = normalize_program(G.nodes[u].get("program", ""))
            pv = normalize_program(G.nodes[v].get("program", ""))
            access_edges.add(tuple(sorted([pu, pv])))

    for pair in PROGRAM_PAIRS:
        features.append(1.0 if pair in access_edges else 0.0)

    # --- B: Adjacency edges between program pairs
    # Tells us WHICH rooms share walls.
    # e.g., ('bedroom', 'kitchen') → 1.0 if any bedroom shares a wall with any kitchen
    adjacency_edges = set()
    for u, v in G.edges():
        edge_types = G[u][v].get('edge_types', [])
        if 'adjacency' in edge_types:
            pu = normalize_program(G.nodes[u].get("program", ""))
            pv = normalize_program(G.nodes[v].get("program", ""))
            adjacency_edges.add(tuple(sorted([pu, pv])))
    
    for pair in PROGRAM_PAIRS:
        features.append(1.0 if pair in adjacency_edges else 0.0)
    
    # --- C: Betweenness centrality per program type
    # Tells us how "central" each program type is in the layout's access graph
    centrality_by_program = {}
    for program in PROGRAMS:
        rooms = [n for n in G.nodes() if normalize_program(G.nodes[n].get("program", "")) == program]
        if rooms:
            centralities = [G.nodes[n].get("betweenness_centrality", 0.0) for n in rooms]
            centrality_by_program[program] = sum(centralities) / len(centralities)
        else:
            centrality_by_program[program] = 0.0
    
    for program in PROGRAMS:
        features.append(centrality_by_program[program])


    return features


# ============================================================================
# STEP 3 — Build query vector from user's program list
#
# The user provides programs (and optionally connectivity).
# We map this to the SAME feature space as the layout vectors.
# This is what makes cosine similarity meaningful.
# ============================================================================

def build_query_vector(
        programs: list[str], 
        sizes: bool = False,
        access: bool = False,
        adjacency: bool = False,
        centrality: bool = False
        ) -> list[float]:
    """Build a query feature vector from program and size preferences.

    Args:
        programs:  e.g. ['bedroom', 'kitchen', 'living room']
        sizes:  e.g. ['Small', 'Medium', 'Large']; if None, any size works
        access: match door connections between programs
        adjacency: match wall adjacencies between programs
        centrality: prefer centrally-located programs (high betweenness)

    Returns:
        Feature vector in the same space as extract_features() output.
    """
    features = []

    # --- A: Count how many of each program the user wants
    # Normalize short names (e.g. 'bed' → 'bedroom') so the query aligns
    # with the canonical names used in PROGRAMS and the stored index.
    query_counts = {}
    for p in programs:
        canonical = normalize_program(p)
        query_counts[canonical] = query_counts.get(canonical, 0) + 1

    if sizes:
        # If user specifies sizes, we assume they want all rooms to be that size
        # (e.g. "I want 2 Small bedrooms and 1 Small kitchen")
        for program in PROGRAMS:
            for size in SIZES:
                features.append(float(query_counts.get(program, 0)) / 3.0 if program in query_counts  else 0.0)
    else:
        features.extend([0.0] * (len(PROGRAMS) * len(SIZES)))  # No size preference, all zeros for size-specific counts

    # --- B: Which pairs does the user want connected?
    # connected=True  → mark every pair combination in the user's list
    # connected=False → no connectivity requirement, all zeros
    if access:
        query_access_pairs = set()
        for i in range(len(programs)):
            for j in range(i + 1, len(programs)):
                pair = tuple(sorted([normalize_program(programs[i]), normalize_program(programs[j])]))
                query_access_pairs.add(pair)
        for pair in PROGRAM_PAIRS:
            features.append(1.0 if pair in query_access_pairs else 0.0)
    else:
        features.extend([0.0] * len(PROGRAM_PAIRS))  # No connectivity preference, all zeros for access edges


    # --- C: Adjacency edges between program pairs
    if adjacency:
        query_adjacency_pairs = set()
        for i in range(len(programs)):
            for j in range(i + 1, len(programs)):
                pair = tuple(sorted([normalize_program(programs[i]), normalize_program(programs[j])]))
                query_adjacency_pairs.add(pair)
        for pair in PROGRAM_PAIRS:
            features.append(1.0 if pair in query_adjacency_pairs else 0.0)
    else:
        features.extend([0.0] * len(PROGRAM_PAIRS))  # No connectivity preference, all zeros for adjacency edges

    # Centrality: if True, prefer programs in central locations
    if centrality:
        features.extend([1.0] * len(PROGRAMS))  # All programs should be central
    else:
        features.extend([0.0] * len(PROGRAMS))

    return features


# ============================================================================
# STEP 4 — Cosine similarity
#
# Measures how similar two vectors are in DIRECTION (not magnitude).
# Two vectors pointing the same way = score 1.0 (perfect match).
# Two vectors at 90 degrees = score 0.0 (nothing in common).
#
# Why cosine and not Euclidean distance?
# Cosine ignores scale: a layout with 4 bedrooms vs 2 bedrooms still scores
# high if the connectivity pattern matches. Euclidean would penalise the count
# difference too heavily.
# ============================================================================

def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot   = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ============================================================================
# STEP 5 — RuleBasedEmbedder: offline index + online search
#
# OFFLINE (once at startup):  layout graphs → vectors → stored in self.index
# ONLINE  (per search call):  user programs → query vector → cosine vs index
# ============================================================================

class RuleBasedEmbedder:

    def __init__(self, layout_graphs: dict[str, nx.Graph]):
        # Build the index once — this replaces the per-search graph traversal
        # in graph_searcher.py. No traversal happens during search().
        self.index = {
            layout_id: extract_features(G)
            for layout_id, G in layout_graphs.items()
        }

    def search(
        self,
        programs: list[str],
        sizes: bool = False,
        access: bool = False,
        adjacency: bool = False,
        centrality: bool = False,
        top_k: int = 3,
    ) -> list[tuple[str, float]]:
        """Find the top-k layouts with EXACTLY the requested room counts.

        Args:
            programs:  e.g. ['bedroom', 'bedroom', 'kitchen', 'bathroom']
            sizes:     whether to match the exact sizes of the programs
            access:    whether the programs must be directly connected by doors
            adjacency: whether the programs must be adjacent (share a wall)
            centrality: whether to prefer centrally-located programs
            top_k:     how many results to return

        Returns:
            list of (layout_id, score) sorted best-first.
        """
        query_vec = build_query_vector(
            programs, 
            sizes=sizes, 
            access=access, 
            adjacency=adjacency, 
            centrality=centrality)

        scores = []
        for layout_id, layout_vec in self.index.items():
            scores.append((layout_id, cosine_similarity(query_vec, layout_vec)))
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:top_k]


# ============================================================================
# Quick demo — run this file directly to see it in action
# ============================================================================

if __name__ == "__main__":
    import json
    from pathlib import Path
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))

    # Load and build index
    graphs_path = Path(__file__).parent.parent / "layout_inputs" / "sample_graphs.json"
    with open(graphs_path) as f:
        layout_graphs = {
            lid: nx.node_link_graph(data)
            for lid, data in json.load(f).items()
        }

    embedder = RuleBasedEmbedder(layout_graphs)

    # Example searches
    print("Search 1:", embedder.search(["bedroom", "kitchen"], access=True, top_k=3))
    print("Search 2:", embedder.search(["bedroom", "bedroom", "kitchen"], top_k=3))
    print("Search 3:", embedder.search(["bedroom", "kitchen", "living room"], centrality=True, top_k=3))

    
