"""Rule-based graph embedder — no ML model required.

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
# ============================================================================

# All program types we care about (determines vector dimensions for room counts)
PROGRAMS = ["bedroom", "living room", "bathroom", "extra", "walkincloset"]

SIZES = ["small", "medium", "large"]

# All program-pair edges we care about
PROGRAM_PAIRS = [
    ("bedroom",     "living room"),
    ("bedroom",     "bathroom"),
    ("bedroom",     "extra"),
    ("bedroom",     "walkincloset"),
    ("bedroom",     "bedroom"),
    ("living room", "bathroom"),
    ("living room", "extra"),
    ("bathroom",    "extra"),
    ("bathroom",    "bathroom"),
    ("extra",       "extra"),
]

CONNECTIVITY_LEVELS = ['peripheral', 'connected', 'central']

WINDOW_COUNT = [0, 1, 2]

# Hard filter tolerances for boundary matching
AREA_TOLERANCE = 20.0
ASPECT_RATIO_TOLERANCE = 0.5
COMPACTNESS_TOLERANCE = 0.2


# Maps short dataset program names to the canonical long names
# used throughout this codebase. Apply at graph-load time via normalize_program()
# so all downstream code works with one consistent vocabulary.
PROGRAM_NORMALIZE: dict[str, str] = {
    "bed":    "bedroom",
    "bath":   "bathroom",
    "living": "living room",
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
      - Betweenness centrality per program type (peripheral == 0.0 /connected <= 0.4 /central > 0.4)
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

    # --- C: Adjacency edges between program pairs
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
    
    # --- D: Betweenness centrality per program type
    # Tells us how "central" each program type is in the layout's access graph
    program_connectivity_counts = {}
    for node in G.nodes():
        program = normalize_program(G.nodes[node].get("program", ""))
        connectivity = G.nodes[node].get("connectivity", "peripheral")
        key = (program, connectivity)
        program_connectivity_counts[key] = program_connectivity_counts.get(key, 0) + 1

    for program in PROGRAMS:
        for level in CONNECTIVITY_LEVELS:
            features.append(float(program_connectivity_counts.get((program, level), 0)))

    # --- E: Window exposure per program type
    # Counts how many rooms of each program type have 0, 1, or 2 facade exposures
    program_window_counts = {}
    for node in G.nodes():
        program = normalize_program(G.nodes[node].get("program", ""))
        windows = G.nodes[node].get("windows", 0)
        windows = min(windows, 2)  # cap at 2
        key = (program, windows)
        program_window_counts[key] = program_window_counts.get(key, 0) + 1

    for program in PROGRAMS:
        for w in WINDOW_COUNT:
            features.append(float(program_window_counts.get((program, w), 0)))

    # --- F: Boundary shape
    # shape: one-hot encoding [rectangular, L-shape, other]
    shape = G.graph.get('shape', 'other') # default to 'other' if not specified
    features.append(1.0 if shape == 'rectangular' else 0.0)
    features.append(1.0 if shape == 'L-shape'     else 0.0)
    features.append(1.0 if shape == 'other'        else 0.0)


    return features


# ============================================================================
# STEP 3 — Build query vector from user's program list
#
# The user provides programs (and optionally connectivity).
# We map this to the SAME feature space as the layout vectors.
# This is what makes cosine similarity meaningful.
# ============================================================================

def build_query_vector(
        programs: list[str | tuple[str, str]], # Can be list[str] or list[tuple[str, str]]
        access_pairs: Optional[list[tuple[str, str]]] = None,
        adjacency_pairs: Optional[list[tuple[str, str]]] = None,
        centrality: Optional[list[tuple[str, str]]] = None,
        windows: Optional[list[tuple[str, int]]] = None,
        shape: Optional[str] = None,  # 'rectangular' | 'L-shape' | 'other' | None
        ) -> list[float]:
    """Build a query feature vector from program and size preferences.

    Args:
        programs: Mixed list of:
            - str: 'bedroom' → any size
            - tuple: ('bedroom', 'large') → exact size
        access_pairs: list of program pairs that should be connected by doors
        adjacency_pairs: list of program pairs that should share walls
        centrality: prefer centrally-located programs (peripheral == 0.0 /connected <= 0.4 /central > 0.4)
        windows:         List of (program, window_count) tuples
        shape:          Preferred apartment shape ('rectangular' | 'L-shape' | 'other')
    Returns:
        Feature vector in the same space as extract_features() output.
    """
    features = []

    # --- A: Parse mixed format (strings and tuples)
    query_counts = {}
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

    # --- D: Connectivity centrality preference
    query_connectivity_counts = {}
    if centrality:
        for program, level in centrality:
                canonical = normalize_program(program)
                key = (canonical, level)
                query_connectivity_counts[key] = query_connectivity_counts.get(key, 0) + 1

    for program in PROGRAMS:
        for level in CONNECTIVITY_LEVELS:
            features.append(float(query_connectivity_counts.get((program, level), 0)))

    # --- E: Window exposure per program type
    query_window_counts = {}
    if windows:
        for program, w in windows:
            canonical = normalize_program(program)
            key = (canonical, w)
            query_window_counts[key] = query_window_counts.get(key, 0) + 1

    for program in PROGRAMS:
        for w in WINDOW_COUNT:
            features.append(float(query_window_counts.get((program, w), 0)))

    # --- F: Boundary shape
    # Shape: one-hot — if None, all zeros (no preference)
    if shape is not None:
        features.append(1.0 if shape == 'rectangular' else 0.0)
        features.append(1.0 if shape == 'L-shape'     else 0.0)
        features.append(1.0 if shape == 'other'        else 0.0)
    else:
        features.extend([0.0, 0.0, 0.0])

    # Aspect ratio and compactness handled as hard filters in search() — not included in query vector since they are not part of the layout vectors.

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
        self.layout_graphs = layout_graphs
        self.index = {
            layout_id: extract_features(G)
            for layout_id, G in layout_graphs.items()
        }

        # Fast lookup for hard filters — no graph traversal at query time  
        self.metadata = {
            layout_id: {
                'total_area':   G.graph.get('total_area', 0.0),
                'aspect_ratio': G.graph.get('aspect_ratio', 1.0),
                'compactness':  G.graph.get('compactness', 1.0),           
            }
            for layout_id, G in layout_graphs.items()
        }     

    def search(
        self,
        programs: list,
        access_pairs: Optional[list[tuple[str, str]]] = None,
        adjacency_pairs: Optional[list[tuple[str, str]]] = None,
        not_adjacency_pairs: Optional[list[tuple[str, str]]] = None,
        centrality: Optional[list[tuple[str, str]]] = None,
        windows: Optional[list[tuple[str, int]]] = None,
        shape: Optional[str] = None,
        total_area: Optional[float] = None,
        aspect_ratio: Optional[float] = None,
        compactness: Optional[float] = None,
        top_k: int = 3,
    ) -> list[tuple[str, float]]:
        """Find the top-k layouts with AT LEAST the requested room counts.

        Args:
            programs: Either:
                - ['bedroom', 'kitchen', 'living room'] → match any sizes
                - [('bedroom', 'Large'), ('kitchen', 'Small')] → match exact sizes
            access_pairs:    whether the programs must be directly connected by doors
            adjacency_pairs: whether the programs must be adjacent (share a wall)
            not_adjacency_pairs: whether the programs must NOT be adjacent (share a wall)
            centrality:     List of (program, connectivity) tuples (peripheral == 0.0 /connected <= 0.4 /central > 0.4)
            windows:         List of (program, window_count) tuples
            shape:          Preferred apartment shape ('rectangular' | 'L-shape' | 'other')
            aspect_ratio:   Preferred aspect ratio
            compactness:    Preferred compactness
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
            
        # Build excluded pairs set
        excluded_pairs = set()
        if not_adjacency_pairs:
            for p1, p2 in not_adjacency_pairs:
                p1_normalized = normalize_program(p1)
                p2_normalized = normalize_program(p2)
                pair = tuple(sorted([p1_normalized, p2_normalized]))
                excluded_pairs.add(pair)
        
        
        def check_required_counts(layout_vec: list[float]) -> bool:
            """Exact count for requested programs only, ignore unmentioned ones."""

            # Merge size_specific and any_size into total required per program
            total_reqs = dict(any_size_reqs)  # start from any-size counts
            for (program, size), count in size_specific_reqs.items():
                total_reqs[program] = total_reqs.get(program, 0) + count

            # Check any-size requirements
            for program, required_count in total_reqs.items():
                if program not in PROGRAMS:
                    continue
                prog_idx = PROGRAMS.index(program)
                total_count = sum(layout_vec[prog_idx * len(SIZES) + s] for s in range(len(SIZES)))
                if total_count < required_count:
                    return False

            # Check size-specific counts within that program
            for (program, size), required_count in size_specific_reqs.items():
                if program not in PROGRAMS or size not in SIZES:
                    continue
                prog_idx = PROGRAMS.index(program)
                size_idx = SIZES.index(size)
                vec_idx = prog_idx * len(SIZES) + size_idx
                if layout_vec[vec_idx] < required_count:  # AT LEAST for size-specific
                    return False
            
            return True   
        
        def has_excluded_adjacencies(layout_id: str) -> bool:
            """Return True if layout has any of the excluded adjacencies."""
            if not excluded_pairs:
                return False
            
            G = self.layout_graphs[layout_id]
            for u, v in G.edges():
                if 'adjacency' in G[u][v].get('edge_types', []):
                    pu = normalize_program(G.nodes[u].get("program", ""))
                    pv = normalize_program(G.nodes[v].get("program", ""))
                    pair = tuple(sorted([pu, pv]))
                    if pair in excluded_pairs:
                        return True
            return False

        query_vec = build_query_vector(
            programs, 
            access_pairs=access_pairs, 
            adjacency_pairs=adjacency_pairs, 
            centrality=centrality,
            windows=windows,
            shape=shape)

        scores = []
        for layout_id, layout_vec in self.index.items():
            meta = self.metadata[layout_id]

            # Hard filters
            if total_area is not None:
                if abs(meta['total_area'] - total_area) > AREA_TOLERANCE:
                    continue
            if aspect_ratio is not None:
                if abs(meta['aspect_ratio'] - aspect_ratio) > ASPECT_RATIO_TOLERANCE:
                    continue
            if compactness is not None:
                if abs(meta['compactness'] - compactness) > COMPACTNESS_TOLERANCE:
                    continue
            if not check_required_counts(layout_vec):
                continue
            if has_excluded_adjacencies(layout_id):
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

    #Program test
    print("Search 1:",  #expected: layout-4
          embedder.search(
          ["walkincloset"], top_k=3))
    
    #Program test
    print("Search 2:",  #expected: layout-1
          embedder.search(
          ["bedroom"], top_k=3))
    
    #Size requirements test
    print("Search 3:", 
          embedder.search( #expected: layout-2
          [('bedroom', 'medium'), ('bedroom', 'small')], 
          top_k=3))

    #Program + size requirements test
    print("Search 4:", 
          embedder.search( # 1 large bedroom + 1 bedroom and 2 bathroom expected: layout-3 and 6
        [('bedroom', 'large'), "bedroom", 'bathroom', 'bathroom'], 
        top_k=3))

    #Shape requirement test
    print("Search 5:", 
          embedder.search( #expected: layout-6
              ["bedroom", "bedroom"], 
              shape='L-shape',
              top_k=3))
    
    #Adjacency + aspect ratio test
    print("Search 6:", 
      embedder.search( # expected: layout-2 and 3
          ["bedroom", "bedroom", "extra", "extra"], 
          adjacency_pairs=[("bedroom", "bedroom")],
          aspect_ratio=1.0,
          top_k=3))

    #Aspect ratio test
    print("Search 7:", 
      embedder.search( #expected: layout-1 (layout-4 excluded: has 2 extras, not 1, layout-5 excluded: aspect ratio 3.75 too far from 2.0)
          ["extra"],
          aspect_ratio=2.0,
          top_k=3))
    
    #Not adjacency test
    print("Search 8:", 
      embedder.search( #expected: layout-2
          ["bedroom", "bedroom"], 
          not_adjacency_pairs=[("bedroom", "bathroom")], 
          top_k=3))
    
    #Windows test
    print("Search 9:",  # expected: layout-1
          embedder.search(
          ["bathroom"],
          windows=[('bathroom', 1)],
          top_k=3))
    
    #Centrality test
    print("Search 10:",  # expected: layout-4
          embedder.search(
          ["living room"],
          centrality=[('bedroom', 'central')],
          top_k=3))
    
    #Area and aspect ratio test
    print("Search 11:",  # expected: layout-3
          embedder.search(
          ["living room"],
          total_area=110.0,
          aspect_ratio=1.0,
          top_k=3))