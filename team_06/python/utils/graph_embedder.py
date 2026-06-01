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
PROGRAMS = ["bedroom", "kitchen", "living room", "bathroom", "dining room", "foyer", "extra"]

SIZES = ["small", "medium", "large"]

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
    ("bedroom",     "bedroom"),
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
        size = G.nodes[node].get("size", "medium")
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
        if 'access' in G[u][v].get('edge_types', []):
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
        if 'adjacency' in G[u][v].get('edge_types', []):
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
        programs: list, # Can be list[str] or list[tuple[str, str]]
        access_pairs: Optional[list[tuple[str, str]]] = None,
        adjacency_pairs: Optional[list[tuple[str, str]]] = None,
        centrality: bool = False
        ) -> list[float]:
    """Build a query feature vector from program and size preferences.

    Args:
        programs: Mixed list of:
            - str: 'bedroom' → any size
            - tuple: ('bedroom', 'large') → exact size
        access_pairs: list of program pairs that should be connected by doors
        adjacency_pairs: list of program pairs that should share walls
        centrality: prefer centrally-located programs (high betweenness)

    Returns:
        Feature vector in the same space as extract_features() output.
    """
    features = []
    query_counts = {}

    # --- A: Parse mixed format (strings and tuples)
    for item in programs:
        if isinstance(item, tuple):
            program, size = item
            canonical = normalize_program(program)
            key = (canonical, size)
            query_counts[key] = query_counts.get(key, 0) + 1
        else:
            # String only — will be handled as "any size" with zero counts
            canonical = normalize_program(item)
            for size in SIZES:
                key = (canonical, size)
                query_counts[key] = query_counts.get(key, 0) + 1 / len(SIZES)

    for program in PROGRAMS:
        for size in SIZES:
            features.append(float(query_counts.get((program, size), 0)))

    # --- B: Which pairs does the user want connected?
    # If access_pairs is provided, mark only those pairs as required.
    # If access_pairs is None, no connectivity requirement (all zeros).
    if access_pairs:
        query_access_pairs = set()
        for p1, p2 in access_pairs:
            p1_normalized = normalize_program(p1)
            p2_normalized = normalize_program(p2)
            pair = tuple(sorted([p1_normalized, p2_normalized]))
            query_access_pairs.add(pair)
        for pair in PROGRAM_PAIRS:
            features.append(1.0 if pair in query_access_pairs else 0.0)
    else:
        features.extend([0.0] * len(PROGRAM_PAIRS))  # No connectivity preference, all zeros for access edges


    # --- C: Adjacency edges between program pairs
    # If adjacency_pairs is provided, mark only those pairs as required.
    # If adjacency_pairs is None, no adjacency requirement (all zeros).
    if adjacency_pairs:
        query_adjacency_pairs = set()
        for p1, p2 in adjacency_pairs:
            p1_normalized = normalize_program(p1)
            p2_normalized = normalize_program(p2)
            pair = tuple(sorted([p1_normalized, p2_normalized]))
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
        programs: list,
        access_pairs: Optional[list[tuple[str, str]]] = None,
        adjacency_pairs: Optional[list[tuple[str, str]]] = None,
        centrality: bool = False,
        top_k: int = 3,
    ) -> list[tuple[str, float]]:
        """Find the top-k layouts with AT LEAST the requested room counts.

        Args:
            programs: Either:
                - ['bedroom', 'kitchen', 'living room'] → match any sizes
                - [('bedroom', 'Large'), ('kitchen', 'Small')] → match exact sizes
            access_pairs:    whether the programs must be directly connected by doors
            adjacency_pairs: whether the programs must be adjacent (share a wall)
            centrality: whether to prefer centrally-located programs
            top_k:     how many results to return

        Returns:
            list of (layout_id, score) sorted best-first; empty if no exact match.
        """
        
        size_specific_reqs = {}  # {(program, size): count}
        any_size_reqs = {}       # {program: count}
        
        for item in programs:
            if isinstance(item, tuple):
                program, size = item
                canonical = normalize_program(program)
                key = (canonical, size)
                size_specific_reqs[key] = size_specific_reqs.get(key, 0) + 1
            else:
                canonical = normalize_program(item)
                any_size_reqs[canonical] = any_size_reqs.get(canonical, 0) + 1
            
        def check_required_counts(layout_vec: list[float]) -> bool:
            """Check if layout has AT LEAST the requested (program, size) pairs."""
            for (program, size), required_count in size_specific_reqs.items():
                if program not in PROGRAMS or size not in SIZES:
                    continue
                prog_idx = PROGRAMS.index(program)
                size_idx = SIZES.index(size)
                vec_idx = prog_idx * len(SIZES) + size_idx
                if layout_vec[vec_idx] < required_count:
                    return False
                
            # Check any-size requirements
            for program, required_count in any_size_reqs.items():
                if program not in PROGRAMS:
                    continue
                prog_idx = PROGRAMS.index(program)
                total_count = sum(layout_vec[prog_idx * len(SIZES) + s] for s in range(len(SIZES)))
                if total_count < required_count:
                    return False
            
            return True   
      

        query_vec = build_query_vector(
            programs, 
            access_pairs=access_pairs, 
            adjacency_pairs=adjacency_pairs, 
            centrality=centrality)

        scores = []
        for layout_id, layout_vec in self.index.items():
            if not check_required_counts(layout_vec):
                continue
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
    graphs_path = Path(__file__).parent.parent.parent / "layout_inputs" / "sample_graphs.json"
    with open(graphs_path) as f:
        layout_graphs = {
            lid: nx.node_link_graph(data)
            for lid, data in json.load(f).items()
        }

    embedder = RuleBasedEmbedder(layout_graphs)

    # Example searches
    print("Search 1:", 
      embedder.search(["dining room"], top_k=3))
    
    print("Search 2a:", 
      embedder.search([('bedroom', 'large'), ('bedroom', 'medium')], top_k=3))

    print("Search 2b:", 
      embedder.search([('bedroom', 'large'), ('bedroom', 'medium'), 'extra'], top_k=3))

    print("Search 3a:", 
      embedder.search(["bedroom", "bedroom"], adjacency_pairs=[("bedroom", "bedroom"), ("kitchen", "living room")], top_k=3))
    
    print("Search 3b:", 
      embedder.search(["bedroom", "bedroom", "extra"], adjacency_pairs=[("bedroom", "bedroom"), ("kitchen", "living room")], top_k=3))
