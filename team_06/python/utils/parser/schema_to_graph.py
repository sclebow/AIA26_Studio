"""Convert layout schema to NetworkX graph representation."""

import json
import networkx as nx
from pathlib import Path
from shapely.geometry import Polygon, LineString

# Per-dataset area thresholds (m²) for classifying room size into small/medium/large.
# RPLAN thresholds: calibrated on 100 compact organic layouts (median bed 7.4 m²).
# Planfinder thresholds: calibrated on 546 parametric layouts (median bed 14.6 m²,
#   open-plan living-kitchen-dining median 35 m², proper bathrooms median 5.7 m²).
# Thresholds chosen at roughly the 33rd and 67th area percentile per program type
# so each category contains approximately one third of the dataset's rooms.
SIZE_THRESHOLDS = {
    'rplan': {
        'living':       {'small': 10,  'medium': 14},
        'bed':          {'small': 7,   'medium': 9},
        'bath':         {'small': 2,   'medium': 4},
        'kitchen':      {'small': 3,   'medium': 4},
        'foyer':        {'small': 5,   'medium': 12},
        'dining':       {'small': 5,   'medium': 10},
        'extra':        {'small': 5,   'medium': 10},
        'storage':      {'small': 3,   'medium': 8},
    },
    'planfinder': {
        'living':       {'small': 25,  'medium': 45},
        'bed':          {'small': 11,  'medium': 17},
        'bath':         {'small': 4,   'medium': 7},
        'extra':        {'small': 4,   'medium': 10},
        'walkincloset': {'small': 3,   'medium': 6},
    },
}
_SIZE_THRESHOLDS_DEFAULT = {'small': 10, 'medium': 20}


def _detect_dataset(layout_id: str) -> str:
    """
    Infer which dataset a layout belongs to from its ID format.

    Planfinder IDs follow the parametric naming convention: L_L{len}_W{wid}_...
    RPLAN IDs are sequential integers: layout-1, layout-35, layout-1019, etc.
    Any unrecognised format falls back to RPLAN thresholds.
    """
    return 'planfinder' if layout_id.startswith('L_') else 'rplan'


def classify_room_size(program: str, area: float, dataset: str = 'rplan') -> str:
    """
    Classify a room's area into small / medium / large for a given dataset.

    Uses dataset-specific thresholds because Planfinder rooms are significantly
    larger than RPLAN rooms (median PF bedroom 14.6 m² vs RPLAN 7.4 m²).
    Applying RPLAN thresholds to PF data would classify every PF room as 'large'.

    Args:
        program: room program string (bed, bath, living, kitchen, extra, …)
        area:    room area in m²
        dataset: 'rplan' or 'planfinder'

    Returns:
        'small' | 'medium' | 'large'
    """
    thresholds = (
        SIZE_THRESHOLDS
        .get(dataset, SIZE_THRESHOLDS['rplan'])
        .get(program, _SIZE_THRESHOLDS_DEFAULT)
    )
    if area < thresholds['small']:
        return 'small'
    elif area < thresholds['medium']:
        return 'medium'
    else:
        return 'large'

def classify_betweenness(bc: float) -> str:
    """
    Classify a room's betweenness centrality into one of three connectivity levels.

    Betweenness centrality measures how often a room lies on the shortest path
    between any two other rooms in the ACCESS graph (doors only, not walls).
    In apartment layouts this tells us whether a room is a circulation hub
    (living room, corridor) or a dead-end destination (bedroom, bathroom).

    Thresholds are global — the topological role of a room is the same regardless
    of whether it is a bedroom or a kitchen: does circulation pass through it?

    Categories:
        peripheral  BC == 0.0      No path flows through this room.
                                   Every path between other rooms avoids it.
                                   Typical: bedroom, bathroom, closed kitchen.

        connected   0.0 < BC ≤ 0.4 Some paths pass through this room but it is
                                   not the dominant hub. Typical: foyer, secondary
                                   corridor, or a PF extra room with few neighbours.

        central     BC > 0.4       Most or all paths between rooms pass through
                                   this room. Primary circulation hub.
                                   Typical: living room in RPLAN, main corridor
                                   (extra) in Planfinder.

    Returns:
        'peripheral' | 'connected' | 'central'
    """
    if bc == 0.0:
        return 'peripheral'
    elif bc <= 0.4:
        return 'connected'
    else:
        return 'central'


def count_facade_exposures(room: dict, facades: list) -> int:
    """
    Count how many distinct exterior facades this room shares a wall with.

    A facade is a polyline stored as a list of [x, y] coordinates.
    We build a single LineString per facade and check whether the room polygon's
    boundary intersects it along a line (shared wall), not just at a point (corner).

    Return values:
        0  — fully interior room (bathroom with no exterior wall, corridor, storage)
        1  — single-aspect room (one exterior wall, most bedrooms and living rooms)
        2  — corner room (two exterior walls, e.g. corner bedroom or corner living)

    Why count facades rather than segments:
        RPLAN facades are multi-segment polylines (one facade = 6–8 coordinate pairs).
        PF facades are single segments (one facade = 2 points).
        Counting facade objects gives a consistent 0/1/2 scale across both datasets.
    """
    poly = Polygon(room['geometry'])
    count = 0
    for facade in facades:
        coords = facade.get('geometry', [])
        if len(coords) < 2:
            continue
        facade_line = LineString(coords)
        inter = poly.boundary.intersection(facade_line)
        if inter.is_empty:
            continue
        if inter.geom_type in ('LineString', 'MultiLineString'):
            count += 1
        elif inter.geom_type == 'GeometryCollection':
            if any(g.geom_type in ('LineString', 'MultiLineString') for g in inter.geoms):
                count += 1
    return count


def calculate_centrality_measures(graph: nx.Graph) -> dict:
    """
    Calculate various centrality measures for all nodes in the graph.
    
    Returns a dictionary with centrality type as key and dict of {node: value} as value.
    """
    # Create subgraph with only access edges
    access_subgraph = nx.Graph([(u, v) for u, v, d in graph.edges(data=True) 
                             if 'access' in d.get('edge_types', [])])

    centrality = {
        'betweenness': nx.betweenness_centrality(access_subgraph), # How often a room lies on shortest paths between other rooms (most important for circulation analysis)
        'degree': nx.degree_centrality(access_subgraph), # Count of connections
        'closeness': nx.closeness_centrality(access_subgraph), # Average distance to all other rooms. Best for: Finding "central" rooms
    }
    return centrality

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

    # Detect which dataset this layout belongs to so we use the correct
    # area thresholds for classify_room_size (PF rooms are ~2x larger than RPLAN).
    dataset = _detect_dataset(layout.get('layoutId', ''))
    facades = layout.get('facades', [])

    # Add nodes for each room with name, program, area, size and windows attributes
    for room in layout['rooms']:
        room_id = room['id']
        attrs = room.get('attributes', {})
        program = attrs.get('program', '') or room.get('program', '')
        name = room.get('name', '')
        area = attrs.get('area', 0)
        size = classify_room_size(program, area, dataset=dataset)
        windows = count_facade_exposures(room, facades)
        graph.add_node(room_id, name=name, program=program, area=area, size=size, windows=windows)
    
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
    
    # Calculate centrality measures on complete access graph and add as node attribute (need to do this after all edges are added)
    centrality_measures = calculate_centrality_measures(graph)
    for node in graph.nodes():
        bc = centrality_measures['betweenness'].get(node, 0)
        graph.nodes[node]['betweenness_centrality'] = bc
        graph.nodes[node]['connectivity'] = classify_betweenness(bc)

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

    repo_root = Path(__file__).resolve().parent.parent.parent.parent

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
