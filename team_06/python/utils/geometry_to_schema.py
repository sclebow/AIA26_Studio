import json
from typing import List, Tuple, Dict, Any
from pathlib import Path


def polyline_to_coords(polyline) -> List[Tuple[float, float]]:
    """Convert Rhino Polyline to list of [x, y] coordinates"""
    coords = []
    for i in range(polyline.PointCount):
        pt = polyline.Point(i)
        coords.append([pt.X, pt.Y])
    return coords


def point3d_to_coords(point) -> Tuple[float, float]:
    """Convert Rhino Point3d to [x, y]"""
    return [point.X, point.Y]


def point3d_to_coords(point) -> Tuple[float, float]:
    """Convert Rhino Point3d to [x, y]"""
    return [point.X, point.Y]


def calculate_polygon_area(coords: List[List[float]]) -> float:
    """Calculate polygon area using shoelace formula"""
    if len(coords) < 3:
        return 0.0
    area = 0.0
    for i in range(len(coords) - 1):
        area += coords[i][0] * coords[i + 1][1]
        area -= coords[i + 1][0] * coords[i][1]
    return abs(area) / 2.0


def calculate_polyline_length(coords: List[List[float]]) -> float:
    """Calculate total length of a polyline"""
    if len(coords) < 2:
        return 0.0
    length = 0.0
    for i in range(len(coords) - 1):
        dx = coords[i + 1][0] - coords[i][0]
        dy = coords[i + 1][1] - coords[i][1]
        length += (dx**2 + dy**2) ** 0.5
    return round(length, 2)


def find_adjacent_rooms(door_coords: List[List[float]], rooms_coords: Dict[str, List[List[float]]]) -> List[str]:
    """Find which rooms a door connects to (simple proximity check)"""
    door_pt = door_coords[0]  # Use first point
    adjacent = []
    
    for room_id, coords in rooms_coords.items():
        # Check if door is near room boundary
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]
            dist = point_to_line_distance(door_pt, p1, p2)
            if dist < 0.5:  # Threshold: door within 0.5 units of boundary
                if room_id not in adjacent:
                    adjacent.append(room_id)
                break
    
    return adjacent


def point_to_line_distance(pt: List[float], p1: List[float], p2: List[float]) -> float:
    """Calculate distance from point to line segment"""
    x, y = pt
    x1, y1 = p1
    x2, y2 = p2
    
    denom = (x2 - x1) ** 2 + (y2 - y1) ** 2
    if denom == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    
    t = max(0, min(1, ((x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)) / denom))
    closest_x = x1 + t * (x2 - x1)
    closest_y = y1 + t * (y2 - y1)
    
    return ((x - closest_x) ** 2 + (y - closest_y) ** 2) ** 0.5

def schema_to_desc(schema):
    """
    Convert a layout schema dict (or JSON string) to a simple description string.
    
    Args:
        schema: dict or JSON string representation of layout schema
    
    Returns format:
        "Name (ID). 1 bedroom, 1 bathroom, 1 living room. Area: 600 sqft."
    """
    try:
        # If schema is a string, parse it as JSON first
        if isinstance(schema, str):
            schema = json.loads(schema)
        
        apt = schema.get("apartment", {})
        name = apt.get("name", "?")
        apt_id = apt.get("id", "?")
        area = apt.get("attributes", {}).get("area", 0)
        
        # Count rooms by program
        rooms = schema.get("rooms", [])
        room_counts = {}
        for room in rooms:
            prog = room.get("attributes", {}).get("program", "?")
            room_counts[prog] = room_counts.get(prog, 0) + 1
        
        # Format room counts: "1 bedroom, 2 bathrooms, 1 living room"
        room_str = ", ".join([f"{count} {prog}" for prog, count in sorted(room_counts.items())])
        
        # Simple format
        desc = f"{name} (ID: {apt_id}). {room_str}. Area: {area:.0f} m2."
        return desc
    
    except:
        return "Error parsing schema"
    
def geometry_to_layout_schema(
    crvBounds,
    crv: List,
    u: List[str],
    crvFacade: List = None,
    crvCirc: List = None,
    ptCirc: List = None,
    layout_id: str = "Layout-001",
    apartment_id: str = "apartment-1",
    apartment_name: str = "Sample Apartment"
) -> Dict[str, Any]:
    """
    Convert Grasshopper geometry to extended layout schema
    
    Args:
        crvBounds: Single polyline for building outline
        crv: List of polylines for room boundaries
        u: List of room program names (e.g., ["living room", "bedroom", "kitchen"])
        crvFacade: List of polylines for facade elements
        crvCirc: List of polylines for circulation
        ptCirc: List of Point3d for door locations
        layout_id: ID for the layout
        apartment_id: ID for the apartment
        apartment_name: Name for the apartment
    
    Returns:
        Dictionary with extended layout_schema structure
    """
    
    # Convert bounds
    outline_coords = polyline_to_coords(crvBounds)
    outline_area = calculate_polygon_area(outline_coords)
    
    # Create apartment object
    apartment = {
        "id": apartment_id,
        "name": apartment_name,
        "geometry": outline_coords,
        "attributes": {
            "area": round(outline_area, 2)
        }
    }
    
    # Process rooms
    rooms = []
    rooms_coords = {}
    
    for i, room_polyline in enumerate(crv):
        room_coords = polyline_to_coords(room_polyline)
        room_id = f"room-{i + 1}"
        rooms_coords[room_id] = room_coords
        
        room_program = u[i] if i < len(u) else "unknown"
        room_area = calculate_polygon_area(room_coords)
        
        room = {
            "id": room_id,
            "name": f"{room_program.capitalize()}",

            "geometry": room_coords,
            "attributes": {
                "area": round(room_area, 2),
                "program": room_program
            }
        }
        rooms.append(room)
    
    # Process doors
    doors = []
    if ptCirc:
        for i, door_pt in enumerate(ptCirc):
            door_coords = [point3d_to_coords(door_pt)]
            adjacent_rooms = find_adjacent_rooms(door_coords, rooms_coords)
            
            door = {
                "id": f"door-{i + 1}",
                "name": f"Door {i + 1}",
                "geometry": door_coords,
                "attributes": {
                    "connectsRooms": adjacent_rooms
                }
            }
            doors.append(door)
    
    # Process facades
    facades = []
    if crvFacade:
        for i, facade_polyline in enumerate(crvFacade):
            facade_coords = polyline_to_coords(facade_polyline)
            facade_length = calculate_polyline_length(facade_coords)
            facade = {
                "id": f"facade-{i + 1}",
                "name": f"Facade {i + 1}",
                "geometry": facade_coords,
                "attributes": {
                    "type": "exterior",
                    "length": facade_length
                }
            }
            facades.append(facade)
    
    # Process circulation
    circulation = []
    if crvCirc:
        for i, circ_polyline in enumerate(crvCirc):
            circ_coords = polyline_to_coords(circ_polyline)
            circ_length = calculate_polyline_length(circ_coords)
            circ = {
                "id": f"circulation-{i + 1}",
                "name": f"Circulation {i + 1}",
                "geometry": circ_coords,
                "attributes": {
                    "type": "circulation",
                    "length": circ_length
                }
            }
            circulation.append(circ)
    
    # Build schema
    schema = {
        "layoutId": layout_id,
        "apartment": apartment,
        "outline": outline_coords,
        "rooms": rooms,
        "doors": doors,
        "facades": facades,
        "circulation": circulation,
        "windows": [],
        "furniture": [],
        "mep": [],
        "structure": []
    }
    description = schema_to_desc(schema)
    schema["description"] = description
    return schema
