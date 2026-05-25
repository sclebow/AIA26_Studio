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
        attrs = room.get('attributes', {})
        program = attrs.get('program', '') or room.get('program', '')
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
    
    print(f"Generated and saved {len(graphs_data)} graphs -> {output_path}")


def generate_graphs_from_directory(layouts_dir: str, output_path: str = None) -> None:
    """
    Generate NetworkX graphs from a directory of individual layout JSON files.

    Args:
        layouts_dir: Path to directory containing layout-*.json files
        output_path: Path to save graphs JSON (default: graphs.json inside layouts_dir)
    """
    layouts_dir = Path(layouts_dir)
    layout_files = sorted(layouts_dir.glob("*.json"))

    if not layout_files:
        print(f"No JSON files found in {layouts_dir}")
        return

    graphs_data = {}
    for layout_file in layout_files:
        with open(layout_file, 'r') as f:
            layout_data = json.load(f)
        if 'rooms' not in layout_data or 'doors' not in layout_data:
            continue
        layout_id = layout_data.get('layoutId', layout_file.stem)
        graph = create_graph_from_layout(layout_data)
        graphs_data[layout_id] = nx.node_link_data(graph)

    if output_path is None:
        output_path = str(layouts_dir / "graphs.json")

    with open(output_path, 'w') as f:
        json.dump(graphs_data, f, indent=2)

    print(f"Generated {len(graphs_data)} graphs -> {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate graphs from layout JSON files.")
    parser.add_argument("--dir", help="Directory of individual layout JSON files (e.g. RPLAN_Dataset_R-NB)")
    parser.add_argument("--file", help="Single bundled layouts JSON file (e.g. sample_layouts.json)")
    parser.add_argument("--output", help="Output path for graphs JSON", default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    if args.dir:
        layouts_dir = Path(args.dir) if Path(args.dir).is_absolute() else repo_root / "layout_inputs" / args.dir
        print(f"Generating graphs from directory: {layouts_dir}")
        generate_graphs_from_directory(str(layouts_dir), args.output)
    else:
        layouts_path = Path(args.file) if args.file else repo_root / "layout_inputs" / "sample_layouts.json"
        graphs_path = args.output or str(repo_root / "layout_inputs" / "sample_graphs.json")
        print(f"Generating graphs from: {layouts_path}")
        generate_and_save_graphs(str(layouts_path), graphs_path)

    print("Done!")
