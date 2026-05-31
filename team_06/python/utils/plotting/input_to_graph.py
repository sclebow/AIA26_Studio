import networkx as nx
import matplotlib.pyplot as plt

# Create a new graph
G = nx.Graph()

# Add nodes (rooms)
nodes = ["bedroom_1", "bedroom_2", "bathroom_1", "bathroom_2", "kitchen", "living"]
#nodes = ["bedroom_1", "bedroom_2", "bathroom_1", "kitchen", "living", "extra"]

G.add_nodes_from(nodes)

# Add some edges to connect the rooms
edges = [
    # Each bedroom connects to its private bathroom
    ("bedroom_1", "bathroom_1"),
    ("bedroom_2", "bathroom_2"),
    # Both bedrooms connect to shared common areas
    ("bedroom_1", "living"),
    ("bedroom_2", "living"),
    ("living", "kitchen"),
    ("living", "bathroom_1"),
    ("living", "bathroom_2")
]

G.add_edges_from(edges)

# Print graph information
print(f"Nodes: {list(G.nodes())}")
print(f"Edges: {list(G.edges())}")
print(f"Number of nodes: {G.number_of_nodes()}")
print(f"Number of edges: {G.number_of_edges()}")

# Visualize the graph
plt.figure(figsize=(8, 6))
pos = nx.spring_layout(G, seed=42)
nx.draw_networkx_nodes(G, pos, node_color='lightblue', node_size=1500)
nx.draw_networkx_labels(G, pos, font_size=10, font_weight='bold')
nx.draw_networkx_edges(G, pos, width=2)
plt.title("Room Graph")
plt.axis('off')
plt.tight_layout()
plt.show()