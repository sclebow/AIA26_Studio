"""Convert layout schema to NetworkX graph representation."""

import json
import networkx as nx
from pathlib import Path
from shapely.geometry import Polygon

def classify_room_size(program: str, area: float) -> str:
    """
    Classify room size based on program type and area in m².
    
    Returns one of: 'Small', 'Medium', 'Large'
    """
    # Define size thresholds for each program type
    size_thresholds = {
        'living': {'small': 20, 'medium': 35},
        'bed': {'small': 12, 'medium': 20},
        'bath': {'small': 5, 'medium': 10},
        'kitchen': {'small': 10, 'medium': 18},
        'foyer': {'small': 5, 'medium': 12},
        'extra': {'small': 10, 'medium': 20},
    }
    
    # Default thresholds if program not found
    default_thresholds = {'small': 10, 'medium': 20}
    
    thresholds = size_thresholds.get(program, default_thresholds)
    
    if area < thresholds['small']:
        return 'Small'
    elif area < thresholds['medium']:
        return 'Medium'
    else:
        return 'Large'

def shares_wall(room1, room2):
    """
    Check if two rooms share a wall using Shapely geometry.
    
    Returns True if rooms share a wall (LineString), False otherwise.
    Two rooms share a wall when their boundaries intersect along a LineString
    (not just at a Point).
    """
    # Create Shapely Polygons from room raw coordinates
    poly1 = Polygon(room1['geometry'])
    poly2 = Polygon(room2['geometry'])
    
    # Boundary intersection
    intersection = poly1.boundary.intersection(poly2.boundary)
    
    #if they don't touch at all, return False immediately
    if intersection.is_empty: 
        return False
    
    # Keep only linear parts (shared wall segments), discard Points
    geom_type = intersection.geom_type
    
    if geom_type in ("LineString", "MultiLineString"):
        return True
    # When multiple geometry types result from the intersection (e.g., both a line and a point). The code extracts only the linear parts and checks if any exist.
    elif geom_type == "GeometryCollection":
        lines = [g for g in intersection.geoms
                 if g.geom_type in ("LineString", "MultiLineString")]
        return len(lines) > 0
    else:
        # Only a Point — rooms touch at a corner, not a wall
        return False

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
        area = attrs.get('area', 0)
        size = classify_room_size(program, area)
        graph.add_node(room_id, name=name, program=program, area=area, size=size)
    
    # Add edges based on door connections
    for door in layout['doors']:
        connected_rooms = door['attributes']['connectsRooms']
        # Create edges between all pairs of connected rooms
        for i in range(len(connected_rooms)):
            for j in range(i + 1, len(connected_rooms)):
                room_id_1, room_id_2 = connected_rooms[i], connected_rooms[j]
                if graph.has_edge(room_id_1, room_id_2):
                    graph[room_id_1][room_id_2]['weight'] = graph[room_id_1][room_id_2].get('weight', 1) + 1
                    # Add access to edge_types if not already present
                    edge_types = graph[room_id_1][room_id_2].get('edge_types', [])
                    if 'access' not in edge_types:
                        edge_types.append('access')
                    graph[room_id_1][room_id_2]['edge_types'] = edge_types
                else:
                    graph.add_edge(room_id_1, room_id_2, edge_types=['access'])

    # Check each pair of rooms for shared walls
    rooms = layout['rooms']
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            room1 = rooms[i]
            room2 = rooms[j]
            
            # Check if these two rooms share a wall using Shapely geometry
            if shares_wall(room1, room2):
                room_id_1 = room1['id']
                room_id_2 = room2['id']
                
                # Add or update edge with adjacency info
                if graph.has_edge(room_id_1, room_id_2):
                    # Edge exists, add adjacency type to existing types
                    edge_types = graph[room_id_1][room_id_2].get('edge_types', [])
                    if 'adjacency' not in edge_types:
                        edge_types.append('adjacency')
                    graph[room_id_1][room_id_2]['edge_types'] = edge_types
                else:
                    # New edge, create with adjacency type
                    graph.add_edge(room_id_1, room_id_2, edge_types=['adjacency'])
    
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
