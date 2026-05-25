import json
import networkx as nx
import matplotlib.pyplot as plt
from pathlib import Path
from schema_to_graph import create_graph_from_layout

# Load the JSON file
with open('team_06/layout_inputs/sample_layouts.json', 'r') as f:
    layouts = json.load(f)

# Color map for all layouts
color_map = {
    'bed': 'lightblue',
    'bath': 'lightcoral',
    'kitchen': 'lightgreen',
    'living': 'orange',
    'foyer': 'lightgray',
    'extra': 'plum'
}

# Loop through each layout
for layout_idx, layout in enumerate(layouts):
    G = create_graph_from_layout(layout)

    # Print graph info
    print(f"\n--- Layout {layout_idx}: {layout['apartment']['name']} ---")
    print(f"Nodes: {list(G.nodes())}")
    print(f"Edges: {list(G.edges())}")
    print(f"Number of nodes: {G.number_of_nodes()}")
    print(f"Number of edges: {G.number_of_edges()}")

    # Visualize
    plt.figure(figsize=(10, 8))
    pos = nx.spring_layout(G, seed=42)

    # Create a mapping from room id to program from the original layout
    room_program_map = {room['id']: room['attributes']['program'] for room in layout['rooms']}

    node_colors = []
    for node in G.nodes():
        program = room_program_map.get(node, '')
        color = color_map.get(program, 'lightgray')
        print(f"Node: {node}, Program: '{program}', Color: {color}")
        node_colors.append(color)

    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=1500)
    nx.draw_networkx_labels(G, pos, labels={node: G.nodes[node]['name'] for node in G.nodes()}, font_size=8)
    nx.draw_networkx_edges(G, pos, width=2)
    plt.title(f"Room Graph: {layout['apartment']['name']}")
    plt.axis('off')
    plt.tight_layout()
    #plt.show()
    
    # Save the plot
    output_dir = Path('team_06/layout_inputs/graph_plots')
    filename = output_dir / f"layout_{layout_idx}_{layout['apartment']['name'].replace(' ', '_')}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"Saved: {filename}")
    plt.close()

print(f"\nAll graphs saved to: {output_dir}")