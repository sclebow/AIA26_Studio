import sys
from pathlib import Path

# Add project root to sys.path to enable imports from team_06 package
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parents[3]
sys.path.insert(0, str(project_root))

import json
import networkx as nx
import matplotlib.pyplot as plt
from team_06.python.utils.parser.schema_to_graph import create_graph_from_layout

# Load the JSON file
json_file = project_root / 'team_06' / 'layout_inputs' / 'sample_layouts.json'
with open(json_file, 'r') as f:
    layouts = json.load(f)

# Color map for all layouts
color_map = {
    'bed': '#4A7CA8',
    'bath': '#C8F4F0',
    'kitchen': '#00C7D4',
    'living': '#009FA6',
    'foyer': '#0082C2',
    'dining': '#FFFACD',
    'extra': '#7A8FA3'
}

size_map = {
    'small': 1000,
    'medium': 2000,
    'large': 3000
}

# Loop through each layout
for layout_idx, layout in enumerate(layouts, start=1):
    G = create_graph_from_layout(layout)

    # Print graph info
    print(f"\n--- Layout {layout_idx}: {layout['layoutId']} ---")
    print(f"Nodes: {list(G.nodes())}")
    print(f"Number of nodes: {G.number_of_nodes()}")

    # Visualize
    plt.figure(figsize=(10, 8))
    pos = nx.spring_layout(G, seed=42)

    # Create a mapping from room id to program from the original layout
    room_program_map = {room['id']: room['attributes']['program'] for room in layout['rooms']}

    node_colors = []
    node_sizes = []
    for node in G.nodes():
        program = room_program_map.get(node, '')
        color = color_map.get(program, 'lightgray')
        size = G.nodes[node].get('size', 'Medium')
        node_size = size_map.get(size, 2000)
        betweenness_centrality = G.nodes[node].get('betweenness_centrality', 0)
        print(f"Node: {node}, Program: '{program}', Color: {color}, Betweenness Centrality: {betweenness_centrality:.3f}")
        node_colors.append(color)
        node_sizes.append(node_size)

    # Debug: Print edge information
    print(f"Edge details:")
    for u, v, d in G.edges(data=True):
        edge_types = d.get('edge_types', [])
        weight = d.get('weight', 0)
        print(f"  {u} -- {v}: types={edge_types}")

    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes)
    nx.draw_networkx_labels(G, pos, labels={node: f"{G.nodes[node]['name']}\n{G.nodes[node]['area']}\nBC: {G.nodes[node].get('betweenness_centrality', 0):.2f}" for node in G.nodes()}, font_size=7)
    
    # Draw edges by type
    access_edges = [(u, v) for u, v, d in G.edges(data=True) if 'access' in d.get('edge_types', [])]
    adjacency_edges = [(u, v) for u, v, d in G.edges(data=True) if 'adjacency' in d.get('edge_types', [])]
    
    if access_edges:
        nx.draw_networkx_edges(G, pos, edgelist=access_edges, width=2, style='solid', edge_color='black', 
                               connectionstyle='arc3,rad=-0', arrows=True, arrowstyle='-', label='Access (doors)')
    if adjacency_edges:
        nx.draw_networkx_edges(G, pos, edgelist=adjacency_edges, width=2, style='dashed', edge_color='blue', 
                               connectionstyle='arc3,rad=0.1', arrows=True, arrowstyle='-', label='Adjacency (shared walls)')
    
    plt.legend(loc='upper left', fontsize=8)
    plt.title(f"Room Graph: {layout['layoutId']}")
    plt.axis('off')
    plt.tight_layout()
    #plt.show()
    
    # Save the plot
    output_dir = project_root / 'team_06' / 'layout_inputs' / 'graph_plots'
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"layout-{layout_idx}_{layout['layoutId'].replace(' ', '_')}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"Saved: {filename}")
    plt.close()

print(f"\nAll graphs saved to: {output_dir}")