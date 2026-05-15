"""Convert layout schema to NetworkX graph representation."""

import json
import networkx as nx
from pathlib import Path

def create_graph_from_layout(layout: dict) -> nx.Graph:
    """Create a NetworkX graph from a layout JSON object.
    
    Nodes are room IDs with program attributes (preserves count).
    Edges represent doors connecting rooms.
    """
    graph = nx.Graph()
    
    # Add nodes for each room with program attribute
    for room in layout['rooms']:
        room_id = room['id']
        program = room.get('program', '')
        name = room.get('name', '')
        graph.add_node(room_id, name=name, program=program)
    
    # Add edges based on door connections
    for door in layout['doors']:
        connected_rooms = door['attributes']['connectsRooms']
        # Create edges between all pairs of connected rooms
        for i in range(len(connected_rooms)):
            for j in range(i + 1, len(connected_rooms)):
                room_id_1, room_id_2 = connected_rooms[i], connected_rooms[j]
                if graph.has_edge(room_id_1, room_id_2):
                    graph[room_id_1][room_id_2]['weight'] = graph[room_id_1][room_id_2].get('weight', 1) + 1
                else:
                    graph.add_edge(room_id_1, room_id_2, weight=1)
    
    return graph





def generate_and_save_graphs(layouts_path: str, output_path: str = None) -> None:
    """
    Generate NetworkX graphs from all layouts and save to JSON.
    
    Args:
        layouts_path: Path to sample_layouts.json
        output_path: Path to save graphs (default: sample_graphs.json in same directory)
    """
    # Load layouts
    with open(layouts_path, 'r') as f:
        layouts = json.load(f)
    
    # Generate graphs
    graphs_data = {}
    for layout_idx, layout_data in enumerate(layouts, 1):
        layout_id = f"layout-{layout_idx}"
        graph = create_graph_from_layout(layout_data)
        # Convert NetworkX graph to JSON-serializable format (node-link)
        graphs_data[layout_id] = nx.node_link_data(graph)
    
    # Save to JSON
    if output_path is None:
        output_path = str(Path(layouts_path).parent / "sample_graphs.json")
    
    with open(output_path, 'w') as f:
        json.dump(graphs_data, f, indent=2)
    
    print(f"✓ Generated and saved {len(graphs_data)} graphs → {output_path}")


if __name__ == "__main__":
    # Get paths
    repo_root = Path(__file__).resolve().parent.parent
    layouts_path = repo_root / "layout_inputs" / "sample_layouts.json"
    graphs_path = repo_root / "layout_inputs" / "sample_graphs.json"
    
    print(f"Generating graphs from: {layouts_path}")
    print(f"Saving to: {graphs_path}\n")
    
    generate_and_save_graphs(str(layouts_path), str(graphs_path))
    print("✓ Done!")
