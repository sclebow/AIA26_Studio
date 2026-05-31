"""
GHPython component: Creates a polyline from the shortest_path tool output.

INPUTS:
    json_str     (str)  - The JSON output from the shortest_path script (connect to 'a' output)
    target_room  (str)  - The destination room name (e.g. "kitchen", "wc1", "bedroom1")
    layout_json  (str)  - The layout JSON string (same one fed to shortest_path)

OUTPUTS:
    polyline  (Polyline) - The path as a polyline through door positions
    points    (list)     - The individual points along the path
    info      (str)      - Description of the path
"""

import json
import Rhino.Geometry as rg

# Parse inputs
result = json.loads(json_str)
layout = json.loads(layout_json)

# Check for errors in the shortest_path output
if "error" in result:
    info = "Error: " + result["error"]
    polyline = None
    points = []
else:
    start_room = result["start_room"]

    # Find the target room in the results to get its path_doors
    path_doors = None
    depth = None
    for room in result["rooms"]:
        if room["room"] == target_room:
            path_doors = room["path_doors"]
            depth = room["depth_from_entry"]
            break

    if path_doors is None:
        info = "Room '{}' not found in results.".format(target_room)
        polyline = None
        points = []
    elif len(path_doors) == 0:
        info = "Target is the start room - no path needed."
        polyline = None
        points = []
    else:
        # Build a lookup of door positions by ID
        door_positions = {}
        for door in layout["doors"]:
            door_positions[door["id"]] = door["position"]

        # Build the polyline points: start centroid -> door1 -> door2 -> ... -> end centroid
        # Calculate room centroids from geometry if available, otherwise use first door position
        def get_room_centroid(layout, room_name):
            """Try to get room centroid from geometry, fallback to average of connected door positions."""
            # Check if rooms have geometry
            for room in layout["rooms"]:
                if room["name"] == room_name or room.get("id") == room_name:
                    geom = room.get("geometry")
                    if geom and len(geom) > 0:
                        xs = [p[0] for p in geom]
                        ys = [p[1] for p in geom]
                        return [sum(xs) / len(xs), sum(ys) / len(ys)]
            # Fallback: average position of doors connected to this room
            room_id = None
            for room in layout["rooms"]:
                if room["name"] == room_name:
                    room_id = room.get("id", room_name)
                    break
            if room_id:
                connected_positions = []
                for door in layout["doors"]:
                    if room_id in door["connects"]:
                        connected_positions.append(door["position"])
                if connected_positions:
                    avg_x = sum(p[0] for p in connected_positions) / len(connected_positions)
                    avg_y = sum(p[1] for p in connected_positions) / len(connected_positions)
                    return [avg_x, avg_y]
            return None

        # Collect ordered points
        path_points_2d = []

        # Start point (centroid of start room)
        start_centroid = get_room_centroid(layout, start_room)
        if start_centroid:
            path_points_2d.append(start_centroid)

        # Door positions along the path (in order)
        for door_id in path_doors:
            pos = door_positions.get(door_id)
            if pos:
                path_points_2d.append(pos)

        # End point (centroid of target room)
        end_centroid = get_room_centroid(layout, target_room)
        if end_centroid:
            path_points_2d.append(end_centroid)

        # Convert to Rhino Point3d (Z = 0)
        points = [rg.Point3d(p[0], p[1], 0) for p in path_points_2d]

        # Create polyline
        if len(points) >= 2:
            polyline = rg.Polyline(points)
            info = "Path from '{}' to '{}': depth={}, doors crossed: {}".format(
                start_room, target_room, depth, " -> ".join(path_doors)
            )
        else:
            polyline = None
            info = "Not enough points to create a polyline."
