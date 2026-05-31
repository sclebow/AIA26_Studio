"""Visualize adjacency graphs (shared walls between rooms)."""

import json
import sys
import networkx as nx
import matplotlib.pyplot as plt
from pathlib import Path

# Add root directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from team_06.python.utils.parser.schema_to_adj_graph import create_adjacency_graph_from_layout

# Load the layout file
with open('team_06/layout_inputs/sample_layouts.json', 'r') as f:
    layouts = json.load(f)

# Process each layout
for layout_idx, layout in enumerate(layouts):
    # Create adjacency graph based on shared walls
    G = create_adjacency_graph_from_layout(layout)

    # Print info
    print(f"\nLayout {layout_idx}:")
    print(f"  Rooms: {G.number_of_nodes()}")
    print(f"  Shared walls: {G.number_of_edges()}")
    
    # Print edge details
    print(f"\n  === Shared Walls ===")
    for u, v, attrs in G.edges(data=True):
        name_u = G.nodes[u]["name"]
        name_v = G.nodes[v]["name"]
        shared_length = attrs.get('shared_length', 0)
        print(f"    {name_u} ↔ {name_v} | wall length = {shared_length} m")

    # Create the plot
    plt.figure(figsize=(12, 9))
    pos = nx.spring_layout(G, seed=42, k=2)

    # Draw the graph
    nx.draw_networkx_nodes(G, pos, node_color='lightblue', node_size=1500)
    
    # Draw labels with room names
    labels = {node: G.nodes[node]['name'] for node in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, font_size=9, font_weight='bold')
    
    # Draw edges with shared wall length labels
    nx.draw_networkx_edges(G, pos, width=2, alpha=0.6)
    
    # Add edge labels (shared wall lengths)
    edge_labels = {(u, v): f"{attrs['shared_length']}m" 
                   for u, v, attrs in G.edges(data=True)}
    nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=8)

    plt.title(f"Room Adjacency Graph - Layout {layout_idx}\n(Numbers = Shared Wall Length in meters)")
    plt.axis('off')
    plt.tight_layout()

    # Save the plot
    output_dir = Path('team_06/layout_inputs/graph_plots')
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"adjacency_layout_{layout_idx}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"\n  Saved: {filename}")
    plt.close()

print(f"\nDone! All plots saved to: team_06/layout_inputs/graph_plots/")
