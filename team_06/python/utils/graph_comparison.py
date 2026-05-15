import networkx as nx
from networkx.algorithms import isomorphism
import matplotlib.pyplot as plt

G1 = nx.Graph()
G1.add_edges_from([(1, 2), (2, 3)])

G2 = nx.Graph()
G2.add_edges_from([('a', 'b'), ('a', 'c')])

# Check if isomorphic
is_isomorphic = nx.is_isomorphic(G1, G2)
print(is_isomorphic)  # True if same structure

# Get the mapping if isomorphic
if is_isomorphic:
    matcher = isomorphism.GraphMatcher(G1, G2)
    mapping = matcher.mapping
    print(mapping)  # Node correspondence

# Visualize both graphs in one figure
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# Plot Graph 1
pos1 = nx.spring_layout(G1, seed=42)
nx.draw_networkx_nodes(G1, pos1, node_color='lightblue', node_size=1500, ax=ax1)
nx.draw_networkx_labels(G1, pos1, font_size=10, font_weight='bold', ax=ax1)
nx.draw_networkx_edges(G1, pos1, width=2, ax=ax1)
ax1.set_title("Room Graph 1", fontsize=12, fontweight='bold')
ax1.axis('off')

# Plot Graph 2
pos2 = nx.spring_layout(G2, seed=42)
nx.draw_networkx_nodes(G2, pos2, node_color='lightgreen', node_size=1500, ax=ax2)
nx.draw_networkx_labels(G2, pos2, font_size=10, font_weight='bold', ax=ax2)
nx.draw_networkx_edges(G2, pos2, width=2, ax=ax2)
ax2.set_title("Room Graph 2", fontsize=12, fontweight='bold')
ax2.axis('off')

plt.tight_layout()
plt.show()