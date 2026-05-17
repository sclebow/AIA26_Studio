"""Graph-based layout search using NetworkX.

Unified topology search: build pattern graphs and match via graph similarity
or exact subgraph isomorphism.
"""

import json
from pathlib import Path
import networkx as nx
from networkx.algorithms import isomorphism

# Import graph builders
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.schema_to_graph import create_graph_from_layout

# ============================================================================
# Helper: parse an edge endpoint — plain program name OR indexed "program:N"
# ============================================================================

def _parse_edge_endpoint(endpoint: str) -> tuple:
    """Return (program, instance_index) from an edge endpoint string.

    Supports two formats:
      "bedroom"   → ('bedroom', 1)   first (and only) bedroom
      "bedroom:2" → ('bedroom', 2)   second bedroom instance
    """
    if ":" in endpoint:
        program, idx = endpoint.rsplit(":", 1)
        return program.strip(), int(idx)
    return endpoint.strip(), 1


# ============================================================================
# Helper function: build topology pattern graph for searches.
# ============================================================================

def build_topology_graph(programs: list, connection_type: str = "any", edges: list = None) -> nx.Graph:
    """Build a SEARCH PATTERN graph from room programs during tool execution.

    This function is called DURING SEARCH:
    1. User says "find layouts with bedroom and kitchen"
    2. LLM calls layout_graph_search with programs=['bedroom', 'kitchen']
    3. local_tool_node calls THIS FUNCTION to build a pattern graph
    4. Pattern is compared against all layout graphs

    Args:
        programs:        Flat list of room types; duplicates = multiple instances.
                         e.g. ['bedroom', 'bedroom', 'kitchen'] → 2 bedrooms + 1 kitchen.
        connection_type: "any"       → no edges (rooms just need to exist).
                         "connected" → fully connected (all rooms paired via doors).
                         Ignored when `edges` is supplied.
        edges:           Explicit connections as program-name pairs OR indexed pairs.

                         Program-level (first instance of each):
                           [["bathroom", "bedroom"], ["kitchen", "store"]]

                         Instance-level (use "program:N" to target a specific instance):
                           [["bedroom:1", "office:1"], ["bedroom:2", "office:2"]]
                           This means bedroom_1 <-> office_1 AND bedroom_2 <-> office_2,
                           which is how you express symmetric / paired connections.

                         Takes precedence over connection_type.
    """
    G = nx.Graph()

    # Create unique node IDs for each program instance (preserves count).
    # ['bedroom', 'bedroom', 'kitchen'] → bedroom_1, bedroom_2, kitchen_1
    program_count = {}
    node_ids = {}
    for idx, program in enumerate(programs):
        count = program_count.get(program, 0) + 1
        program_count[program] = count
        node_id = f"{program}_{count}"
        node_ids[idx] = (node_id, program)
        G.add_node(node_id, program=program)

    if edges is not None:
        # EDGES mode: wire only the specific pairs described.
        # Supports both "bedroom" (→ bedroom_1) and "bedroom:2" (→ bedroom_2).
        for edge_pair in edges:
            if len(edge_pair) == 2:
                prog_a, idx_a = _parse_edge_endpoint(edge_pair[0])
                prog_b, idx_b = _parse_edge_endpoint(edge_pair[1])
                node_a = f"{prog_a}_{idx_a}"
                node_b = f"{prog_b}_{idx_b}"
                if G.has_node(node_a) and G.has_node(node_b) and node_a != node_b:
                    G.add_edge(node_a, node_b)

    elif connection_type == "connected" and len(node_ids) > 1:
        # CONNECTED mode: fully connected graph (complete subgraph).
        node_list = [node_id for node_id, _ in node_ids.values()]
        for i in range(len(node_list)):
            for j in range(i + 1, len(node_list)):
                G.add_edge(node_list[i], node_list[j])
    # else: connection_type == "any" → nodes only, no edges

    return G


# ============================================================================
# GraphSearcher: loads layout graphs and provides search methods.
# ============================================================================

class GraphSearcher:

    def __init__(self, graphs_path: str):
        self.graphs_path = graphs_path
        self.layout_graphs = self._load_graphs()

    # -------------------------------------------------------------------------
    def _load_graphs(self) -> dict:
        with open(self.graphs_path, "r") as f:
            graphs_data = json.load(f)
        return {
            layout_id: nx.node_link_graph(data)
            for layout_id, data in graphs_data.items()
        }

    # -------------------------------------------------------------------------
    def search_by_graph_similarity(self, topology_graph: nx.Graph, method: str = "jaccard") -> list:
        """Rank layouts against a topology pattern at PROGRAM level.

        ALGORITHM:
        1. Extract program counts + required program-pair edges from the pattern.
        2. Filter layouts that don't have enough of each program type.
        3. Extract program-level edges from each layout (only between searched programs).
        4. Score by Jaccard (or overlap) similarity of edge sets.
        5. Tiebreak by connectivity density among the required rooms.

        Returns: [(layout_id, similarity_score), ...] sorted best-first.
        """
        results = []

        # What programs + how many does the user need?
        pattern_programs = {}
        for node in topology_graph.nodes():
            prog = topology_graph.nodes[node].get("program", "")
            pattern_programs[prog] = pattern_programs.get(prog, 0) + 1

        # Required connections at program level (set of sorted 2-tuples).
        pattern_edges = set()
        for u, v in topology_graph.edges():
            prog_u = topology_graph.nodes[u].get("program", "")
            prog_v = topology_graph.nodes[v].get("program", "")
            pattern_edges.add(tuple(sorted([prog_u, prog_v])))

        for layout_id, G in self.layout_graphs.items():
            # Count rooms by program in this layout.
            available = {}
            for node in G.nodes():
                prog = G.nodes[node].get("program", "")
                available[prog] = available.get(prog, 0) + 1

            # Hard filter: must have enough of every required program type.
            if not all(available.get(p, 0) >= c for p, c in pattern_programs.items()):
                continue

            # Extract program-level edges between relevant rooms only.
            layout_edges = set()
            for u, v in G.edges():
                prog_u = G.nodes[u].get("program", "")
                prog_v = G.nodes[v].get("program", "")
                if prog_u in pattern_programs and prog_v in pattern_programs:
                    layout_edges.add(tuple(sorted([prog_u, prog_v])))

            # Similarity score.
            if method == "jaccard":
                union_size = len(pattern_edges | layout_edges)
                similarity = len(pattern_edges & layout_edges) / union_size if union_size else 0.0
            elif method == "overlap":
                min_size = min(len(pattern_edges), len(layout_edges)) or 1
                similarity = len(pattern_edges & layout_edges) / min_size
            else:
                similarity = 0.0

            # Tiebreaker: connectivity density of required rooms in this layout.
            req_nodes = [n for n in G.nodes() if G.nodes[n].get("program", "") in pattern_programs]
            tiebreaker = nx.density(G.subgraph(req_nodes)) if len(req_nodes) > 1 else 0.0

            results.append((layout_id, similarity, tiebreaker))

        results.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return [(lid, sim) for lid, sim, _ in results]

    # -------------------------------------------------------------------------
    def search_by_subgraph_isomorphism(self, pattern_graph: nx.Graph) -> list:
        """Find layouts that contain the EXACT pattern as a subgraph.

        Uses NetworkX VF2 subgraph isomorphism with categorical node matching
        on the 'program' attribute.  This is the only method that can verify
        instance-level structural constraints — e.g. that bedroom_1 connects
        to office_1 AND bedroom_2 connects to office_2 as separate pairs.

        Returns: [layout_id, ...] for every layout where the pattern fits exactly.
                 Empty list if no layout contains the full pattern.
        """
        node_match = isomorphism.categorical_node_match("program", "")
        matched = []
        for layout_id, G in self.layout_graphs.items():
            gm = isomorphism.GraphMatcher(G, pattern_graph, node_match=node_match)
            if gm.subgraph_is_isomorphic():
                matched.append(layout_id)
        return matched

    # -------------------------------------------------------------------------
    def search_hybrid(self, pattern_graph: nx.Graph) -> dict:
        """Two-phase search: exact isomorphism first, Jaccard ranking as fallback.

        Phase 1 — Subgraph isomorphism (exact):
          Layouts where the full instance-level pattern is satisfied.
          These are returned with match_type='exact' and score=1.0.

        Phase 2 — Jaccard similarity (approximate):
          Remaining layouts ranked by how close they come to the program-level
          pattern.  These are returned with match_type='approximate'.

        Returns:
          {
            "exact":       [(layout_id, 1.0), ...],
            "approximate": [(layout_id, score), ...],
          }
        """
        exact_ids = set(self.search_by_subgraph_isomorphism(pattern_graph))
        jaccard_all = self.search_by_graph_similarity(pattern_graph, method="jaccard")

        exact = [(lid, 1.0) for lid in exact_ids]
        approximate = [(lid, score) for lid, score in jaccard_all if lid not in exact_ids]

        return {"exact": exact, "approximate": approximate}

    # -------------------------------------------------------------------------
    def get_layout_info(self, layout_id: str) -> nx.Graph:
        return self.layout_graphs.get(layout_id)

    def get_graph_stats(self, layout_id: str) -> dict:
        G = self.layout_graphs.get(layout_id)
        if G is None:
            return None

        program_counts = {}
        for node in G.nodes():
            prog = G.nodes[node].get("program", "")
            program_counts[prog] = program_counts.get(prog, 0) + 1

        return {
            "layout_id": layout_id,
            "num_rooms": G.number_of_nodes(),
            "num_connections": G.number_of_edges(),
            "room_programs": program_counts,
            "is_connected": nx.is_connected(G),
            "density": nx.density(G),
            "clustering_coefficient": (
                sum(nx.clustering(G).values()) / G.number_of_nodes()
                if G.number_of_nodes() > 0 else 0
            ),
            "degree_sequence": {
                G.nodes[node].get("name", node): G.degree(node) for node in G.nodes()
            },
        }
