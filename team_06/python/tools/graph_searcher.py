"""Graph-based layout search using NetworkX.

Unified topology search: build pattern graphs and match via graph similarity.
"""

import json
from pathlib import Path
import networkx as nx

# Import graph builders
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.graph_embedder import RuleBasedEmbedder

# ============================================================================
# GraphSearcher class: loads layout graphs and provides search methods.
# ============================================================================
class GraphSearcher:
    # --------- Loading and initialization
    def __init__(self, graphs_path: str):

        self.graphs_path = graphs_path
        self.layout_graphs = self._load_graphs()
        self._embedder = RuleBasedEmbedder(self.layout_graphs)
    
    # --------- Private methods
    def _load_graphs(self) -> dict:

        with open(self.graphs_path, 'r') as f:
            graphs_data = json.load(f)
        
        # Convert node-link format back to NetworkX graphs
        layout_graphs = {}
        for layout_id, node_link_data in graphs_data.items():
            layout_graphs[layout_id] = nx.node_link_graph(node_link_data)
        
        return layout_graphs


    def search_by_embedding(
        self,
        programs: list,
        access: bool = False,
        adjacency: bool = False,
        centrality: bool = False,
        top_k: int | None = None,
        candidate_ids: set | None = None,
    ) -> list:
        """Rank layouts by rule-based cosine similarity on pre-built feature vectors.

        Fastest search path — no graph traversal at query time.  The feature
        index is built once in __init__ and reused across all calls.

        Args:
            programs:      room types; duplicates = multiple instances.
            access:        match door connections between programs
            adjacency:     match wall adjacencies between programs
            centrality:    prefer centrally-located program types
            top_k:         max results to return; None = return all that pass.
            candidate_ids: restrict to this subset (for pipeline chaining).

        Returns: [(layout_id, cosine_score), ...] sorted best-first.
        """
        k = top_k if top_k is not None else len(self.layout_graphs)
        results = self._embedder.search(
            programs, 
            access=access, 
            adjacency=adjacency, 
            centrality=centrality, 
            top_k=k)
        
        if candidate_ids is not None:
            results = [(lid, s) for lid, s in results if lid in candidate_ids]
        return results
      
    
    # --------- Utility methods
    # Get layout info for a specific layout ID
    def get_layout_info(self, layout_id: str) -> nx.Graph:
        
        return self.layout_graphs.get(layout_id)
    
    # --------- Statistics
    # Get network statistics for a layout
    def get_graph_stats(self, layout_id: str) -> dict:
        G = self.layout_graphs.get(layout_id)
        if G is None:
            return None
        
        # Count rooms by program
        program_counts = {}
        for node in G.nodes():
            program = G.nodes[node].get('program', '')
            program_counts[program] = program_counts.get(program, 0) + 1
        
        return {
            "layout_id": layout_id,
            "num_rooms": G.number_of_nodes(),
            "num_connections": G.number_of_edges(),
            "room_programs": program_counts,
            "is_connected": nx.is_connected(G),
            "density": nx.density(G),
            "clustering_coefficient": sum(nx.clustering(G).values()) / G.number_of_nodes() if G.number_of_nodes() > 0 else 0,
            "degree_sequence": {G.nodes[node].get('name', node): G.degree(node) for node in G.nodes()}
        }
