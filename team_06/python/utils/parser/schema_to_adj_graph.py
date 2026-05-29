"""Create an adjacency graph based on shared walls between rooms."""

import json
import networkx as nx
from pathlib import Path
from shapely.geometry import Polygon
from shapely.ops import unary_union


def get_shared_wall_info(room1, room2, min_length=1e-6):
    """
    Detect if two rooms share a wall using Shapely geometry.
    
    Returns a dict with 'shared' (bool), 'length', and 'segment' if shared.
    Two rooms share a wall when their boundaries intersect along a LineString
    (not just at a Point).
    """
    poly1 = Polygon(room1['geometry'])
    poly2 = Polygon(room2['geometry'])
    
    # Boundary intersection
    intersection = poly1.boundary.intersection(poly2.boundary)
    
    if intersection.is_empty:
        return {'shared': False}
    
    # Keep only linear parts (shared wall segments), discard Points
    geom_type = intersection.geom_type
    
    if geom_type in ("LineString", "MultiLineString"):
        shared = intersection
    elif geom_type == "GeometryCollection":
        lines = [g for g in intersection.geoms
                 if g.geom_type in ("LineString", "MultiLineString")]
        if not lines:
            return {'shared': False}
        shared = unary_union(lines)
    else:
        # Only a Point — rooms touch at a corner, not a wall
        return {'shared': False}
    
    shared_length = shared.length
    if shared_length < min_length:
        return {'shared': False}
    
    return {
        'shared': True,
        'shared_length': round(shared_length, 4),
        'shared_segment': shared.wkt
    }


def create_adjacency_graph_from_layout(layout: dict) -> nx.Graph:
    """
    Create a NetworkX graph from a layout JSON object based on shared walls.
    
    Nodes are room IDs with attributes (name, program, area).
    Edges represent walls shared between rooms, with attributes (shared_length, shared_segment).
    
    Two rooms share a wall when their boundaries intersect along a LineString
    (collinear segment of non-zero length), NOT just at a Point.
    
    Args:
        layout: Dictionary with 'rooms' key containing room data with 'geometry'
        
    Returns:
        NetworkX graph where edges represent shared walls
    """
    graph = nx.Graph()
    
    # Add a node for each room
    for room in layout['rooms']:
        room_id = room['id']
        attrs = room.get('attributes', {})
        program = attrs.get('program', '') or room.get('program', '')
        name = room.get('name', '')
        area = attrs.get('area', 0)
        graph.add_node(room_id, name=name, program=program, area=area)
    
    # Check each pair of rooms for shared walls
    rooms = layout['rooms']
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            room1 = rooms[i]
            room2 = rooms[j]
            
            # Check if these two rooms share a wall using Shapely geometry
            wall_info = get_shared_wall_info(room1, room2)
            
            if wall_info['shared']:
                room_id_1 = room1['id']
                room_id_2 = room2['id']
                
                # Add an edge with wall attributes
                graph.add_edge(
                    room_id_1, room_id_2,
                    shared_length=wall_info['shared_length'],
                    shared_segment=wall_info['shared_segment']
                )
    
    return graph


def generate_adjacency_graphs_from_directory(layouts_dir: str, output_path: str = None) -> None:
    """
    Generate adjacency graphs from a directory of layout JSON files.
    
    Reads all JSON files from a directory, creates adjacency graphs for each,
    and saves them to a single output JSON file.

    Args:
        layouts_dir: Path to directory containing layout JSON files
        output_path: Path to save graphs JSON (default: adjacency_graphs.json in layouts_dir)
    """
    layouts_dir = Path(layouts_dir)
    layout_files = sorted(layouts_dir.glob("*.json"))

    if not layout_files:
        print(f"No JSON files found in {layouts_dir}")
        return

    graphs_data = {}
    
    # Process each layout file
    for layout_file in layout_files:
        print(f"Processing {layout_file.name}...")
        
        with open(layout_file, 'r') as f:
            layout_data = json.load(f)
        
        # Skip if layout doesn't have required fields
        if 'rooms' not in layout_data:
            print(f"  Skipped: missing 'rooms'")
            continue
        
        layout_id = layout_data.get('layoutId', layout_file.stem)
        graph = create_adjacency_graph_from_layout(layout_data)
        
        # Convert NetworkX graph to JSON format
        graphs_data[layout_id] = nx.node_link_data(graph)
        print(f"  Created graph with {graph.number_of_nodes()} rooms and {graph.number_of_edges()} shared walls")

    # Save all graphs to output file
    if output_path is None:
        output_path = str(layouts_dir / "adjacency_graphs.json")

    with open(output_path, 'w') as f:
        json.dump(graphs_data, f, indent=2)

    print(f"\nDone! Generated {len(graphs_data)} adjacency graphs -> {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate adjacency graphs based on shared walls from layout JSON files."
    )
    parser.add_argument(
        "--dir", 
        help="Directory of layout JSON files to process"
    )
    parser.add_argument(
        "--output", 
        help="Output path for graphs JSON", 
        default=None
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent.parent

    if args.dir:
        layouts_dir = Path(args.dir) if Path(args.dir).is_absolute() else repo_root / "layout_inputs" / args.dir
        print(f"Generating adjacency graphs from directory: {layouts_dir}")
        generate_adjacency_graphs_from_directory(str(layouts_dir), args.output)
    else:
        # Default to team_06 layout inputs
        layouts_dir = repo_root / "team_06" / "layout_inputs"
        if layouts_dir.exists():
            print(f"Generating adjacency graphs from directory: {layouts_dir}")
            generate_adjacency_graphs_from_directory(str(layouts_dir), args.output)
        else:
            print(f"Default directory not found: {layouts_dir}")

