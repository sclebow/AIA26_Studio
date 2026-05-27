"""Graph-based layout search using NetworkX.

Unified topology search: build pattern graphs and match via graph similarity.
"""

import json
from pathlib import Path
import networkx as nx

# Import graph builders
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.parser.schema_to_graph import create_graph_from_layout

# ============================================================================
# GraphSearcher class: loads layout graphs and provides search methods.
# ============================================================================
class GraphSearcher:
    # --------- Loading and initialization
    def __init__(self, graphs_path: str):

        self.graphs_path = graphs_path
        self.layout_graphs = self._load_graphs()
    
    # --------- Private methods
    def _load_graphs(self) -> dict:

        with open(self.graphs_path, 'r') as f:
            graphs_data = json.load(f)
        
        # Convert node-link format back to NetworkX graphs
        layout_graphs = {}
        for layout_id, node_link_data in graphs_data.items():
            layout_graphs[layout_id] = nx.node_link_graph(node_link_data)
        
        return layout_graphs

    def search_by_graph_similarity(self, topology_graph: nx.Graph, method: str = "jaccard") -> list:
        """Search all layouts for matches against a topology pattern.
        
        ALGORITHM:
        1. Extract what user is looking for (program counts + required edges)
        2. For each layout, check if it HAS those programs
        3. Extract program-level edges from the layout
        4. Compare user edges vs layout edges using similarity metric
        5. Rank by similarity + tiebreaker (connectivity)
        
        KEY INSIGHT: We work at PROGRAM LEVEL (bedroom, kitchen, living room),
        not ROOM LEVEL (room-1, room-2). This allows matching ANY bedroom
        to ANY kitchen, regardless of their physical room IDs.
        

        """
        results = []
        
        # STEP 1: Extract what user is looking for from topology pattern
        # Count each program type: {'bedroom': 1, 'kitchen': 1, 'living room': 1}
        pattern_programs = {}
        for node in topology_graph.nodes():
            program = topology_graph.nodes[node].get('program', '')
            pattern_programs[program] = pattern_programs.get(program, 0) + 1
        
        # Extract required PROGRAM-LEVEL edges (not room IDs)
        # E.g., {('bedroom', 'kitchen'), ('kitchen', 'living room')}
        # This is the CONNECTIVITY PATTERN the user wants
        pattern_edges = set()
        for u, v in topology_graph.edges():
            prog_u = topology_graph.nodes[u].get('program', '')
            prog_v = topology_graph.nodes[v].get('program', '')
            edge = tuple(sorted([prog_u, prog_v]))
            pattern_edges.add(edge)
        
        # STEP 2-4: Check each layout
        for layout_id, G in self.layout_graphs.items():
            # Get available programs in this layout
            # Count actual rooms by program type: {'bedroom': 1, 'kitchen': 1, 'living': 2, ...}
            available_programs = {}
            for node in G.nodes():
                program = G.nodes[node].get('program', '')
                available_programs[program] = available_programs.get(program, 0) + 1
            
            # FILTER: Does layout have enough of each program type?
            # E.g., if user wants 2 bedrooms, layout must have at least 2 bedrooms
            if not all(available_programs.get(prog, 0) >= count 
                      for prog, count in pattern_programs.items()):
                continue  # Skip this layout, doesn't match
            
            # EXTRACT: Get program-level edges from the layout
            # Only count edges between programs user cares about
            # E.g., if user wants bedroom+kitchen, ignore bathroom edges
            layout_edges = set()
            for u, v in G.edges():
                prog_u = G.nodes[u].get('program', '')
                prog_v = G.nodes[v].get('program', '')
                # Only count edges between programs we care about
                if prog_u in pattern_programs and prog_v in pattern_programs:
                    edge = tuple(sorted([prog_u, prog_v]))
                    layout_edges.add(edge)
            
            # STEP 5a: Calculate similarity (how well does layout match user's edge pattern?)
            if method == "jaccard":
                # Jaccard: intersection / union
                # How many edges match? divided by total edges needed
                # 2 matching edges out of 3 required = 2/3 = 0.67
                union_size = len(pattern_edges | layout_edges)
                if union_size > 0:
                    similarity = len(pattern_edges & layout_edges) / union_size
                else:
                    similarity = 0.0
            
            elif method == "overlap":
                # Overlap: intersection / min
                # More forgiving than Jaccard
                # 2 matching edges vs min(2 required, 4 in layout) = 2/2 = 1.0
                min_size = min(len(pattern_edges), len(layout_edges)) or 1
                similarity = len(pattern_edges & layout_edges) / min_size
            
            else:
                similarity = 0.0
            
            # STEP 5b: Tiebreaker (if two layouts have same similarity score)
            # Which layout's required rooms are MORE interconnected?
            # E.g., all 3 rooms connected via doors = high density
            #      3 rooms with only 1 door = low density
            required_prog_nodes = [node for node in G.nodes() 
                                  if G.nodes[node].get('program', '') in pattern_programs]
            if len(required_prog_nodes) > 1:
                subgraph = G.subgraph(required_prog_nodes)
                # Density: 0.0 (isolated) to 1.0 (fully connected)
                tiebreaker = nx.density(subgraph)
            else:
                tiebreaker = 0.0
            
            results.append((layout_id, similarity, tiebreaker))
        
        # STEP 6: Sort by similarity first, then by tiebreaker (connectivity)
        results.sort(key=lambda x: (x[1], x[2]), reverse=True)
        
        # Return as (layout_id, similarity) pairs for compatibility
        return [(layout_id, similarity) for layout_id, similarity, _ in results]
    
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
