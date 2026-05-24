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

# ============================================================================
# STEP 1 — Define the feature schema
#
# A fixed list of features we extract from every graph.
# Each graph → a vector of the same length, in the same order.
# The order must never change — adding a new feature invalidates old vectors.
# ============================================================================

# All program types we care about (determines vector dimensions for room counts)
PROGRAMS = ["bedroom", "kitchen", "living room", "bathroom", "dining room", "study"]

# All program-pair edges we care about
# These are the connectivity features: is bedroom directly connected to kitchen?
PROGRAM_PAIRS = [
    ("bedroom",     "kitchen"),
    ("bedroom",     "living room"),
    ("bedroom",     "bathroom"),
    ("kitchen",     "living room"),
    ("kitchen",     "dining room"),
    ("living room", "bathroom"),
    ("living room", "dining room"),
]

# Total vector length = len(PROGRAMS) + len(PROGRAM_PAIRS) + 2 global stats
# = 6 + 7 + 2 = 15 dimensions

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

    Vector layout:
      [0..5]   room counts per program type   (from PROGRAMS)
      [6..12]  edge presence per program pair  (from PROGRAM_PAIRS, 0 or 1)
      [13]     graph density                   (0.0 to 1.0)
      [14]     is_connected                    (0.0 or 1.0)
    """
    features = []

    # --- A: Room counts per program type
    # Tells us HOW MANY of each room type exist in this layout.
    # e.g., PROGRAMS = ['bedroom', 'kitchen', ...]
    #        features = [2.0, 1.0, 1.0, 2.0, 0.0, 0.0]
    #                    ^2 bedrooms ^1 kitchen ^1 living ^2 baths ^0 dining ^0 study
    program_counts = {}
    for node in G.nodes():
        p = G.nodes[node].get("program", "")
        program_counts[p] = program_counts.get(p, 0) + 1

    for program in PROGRAMS:
        features.append(float(program_counts.get(program, 0)))

    # --- B: Edge presence between program pairs
    # Tells us WHICH rooms are directly connected by doors.
    # e.g., ('bedroom', 'kitchen') → 1.0 if any bedroom shares a door with any kitchen
    connected_pairs = set()
    for u, v in G.edges():
        pu = G.nodes[u].get("program", "")
        pv = G.nodes[v].get("program", "")
        connected_pairs.add(tuple(sorted([pu, pv])))

    for pair in PROGRAM_PAIRS:
        features.append(1.0 if pair in connected_pairs else 0.0)

    # --- C: Global graph statistics
    # Density: fraction of possible edges that actually exist (0=sparse, 1=fully connected)
    # is_connected: whether all rooms are reachable from each other
    features.append(nx.density(G))
    features.append(1.0 if nx.is_connected(G) else 0.0)

    return features


# ============================================================================
# STEP 3 — Build query vector from user's program list
#
# The user provides programs (and optionally connectivity).
# We map this to the SAME feature space as the layout vectors.
# This is what makes cosine similarity meaningful.
# ============================================================================

def build_query_vector(programs: list[str], connected: bool = False) -> list[float]:
    """Build a query feature vector from a list of desired program names.

    Args:
        programs:  e.g. ['bedroom', 'kitchen', 'living room']
        connected: True if all programs must be directly connected via doors

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

    for program in PROGRAMS:
        features.append(float(query_counts.get(program, 0)))

    # --- B: Which pairs does the user want connected?
    # connected=True  → mark every pair combination in the user's list
    # connected=False → no connectivity requirement, all zeros
    query_pairs = set()
    if connected:
        for i in range(len(programs)):
            for j in range(i + 1, len(programs)):
                pair = tuple(sorted([programs[i], programs[j]]))
                query_pairs.add(pair)

    for pair in PROGRAM_PAIRS:
        features.append(1.0 if pair in query_pairs else 0.0)

    # --- C: Global stats — not meaningful for a query, leave as zero
    features.append(0.0)
    features.append(0.0)

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
        connected: bool = False,
        top_k: int = 3,
    ) -> list[tuple[str, float]]:
        """Find the top-k layouts with EXACTLY the requested room counts.

        Args:
            programs:  e.g. ['bedroom', 'bedroom', 'kitchen', 'bathroom']
            connected: whether the programs must be directly connected by doors
            top_k:     how many results to return

        Returns:
            list of (layout_id, score) sorted best-first; empty if no exact match.
        """
        required: dict[str, int] = {}
        for p in programs:
            canonical = normalize_program(p)
            required[canonical] = required.get(canonical, 0) + 1

        required_indices = {
            PROGRAMS.index(p): count
            for p, count in required.items()
            if p in PROGRAMS
        }

        query_vec = build_query_vector(programs, connected=connected)

        scores = []
        for layout_id, layout_vec in self.index.items():
            if any(layout_vec[idx] != count for idx, count in required_indices.items()):
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

    graphs_path = Path(__file__).parent.parent / "layout_inputs" / "sample_graphs.json"
    with open(graphs_path) as f:
        graphs_data = json.load(f)

    layout_graphs = {
        lid: nx.node_link_graph(data)
        for lid, data in graphs_data.items()
    }

    # --- Offline phase: build the index once
    embedder = RuleBasedEmbedder(layout_graphs)
    print("Index built. Feature vector length:", len(next(iter(embedder.index.values()))))
    print("Dimensions: PROGRAMS + PROGRAM_PAIRS + density + connected")
    print(f"          = {len(PROGRAMS)} + {len(PROGRAM_PAIRS)} + 1 + 1 = {len(PROGRAMS)+len(PROGRAM_PAIRS)+2}\n")

    # --- Online phase: search queries hit the pre-built index
    queries = [
        (["bedroom", "kitchen"],                False,  "any layout"),
        (["bedroom", "bedroom", "kitchen"],     False,  "2 bedrooms + kitchen, any layout"),
        (["bedroom", "kitchen", "living room"], True,   "all three connected"),
    ]

    for programs, connected, label in queries:
        print(f"Query: {programs} — {label}")
        results = embedder.search(programs, connected=connected, top_k=3)
        for layout_id, score in results:
            print(f"  {layout_id}: {score:.3f}")
        print()
