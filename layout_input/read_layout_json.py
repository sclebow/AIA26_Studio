import json
import os

# ============================================================================
# READ & PARSE layout.json FOR GRASSHOPPER
# ============================================================================

def read_layout_json(file_path):
    """
    Read and parse layout.json file.
    
    Args:
        file_path (str): Path to layout.json file
        
    Returns:
        dict: Parsed JSON data
    """
    try:
        with open(file_path, 'r') as f:
            layout_data = json.load(f)
        return layout_data
    except FileNotFoundError:
        print("Error: File not found at {}".format(file_path))
        return None
    except json.JSONDecodeError as e:
        print("Error: Invalid JSON - {}".format(str(e)))
        return None


def extract_rooms(layout_data):
    """
    Extract room information from layout data.
    
    Args:
        layout_data (dict): Parsed layout JSON
        
    Returns:
        list: List of room dictionaries
    """
    rooms = []
    
    # Adjust key names based on your actual JSON structure
    if 'rooms' in layout_data:
        rooms = layout_data['rooms']
    elif 'layout' in layout_data:
        rooms = layout_data['layout'].get('rooms', [])
    
    return rooms


def extract_windows(layout_data, room_name):
    """
    Extract window data for a specific room.
    
    Args:
        layout_data (dict): Parsed layout JSON
        room_name (str): Name of room to query
        
    Returns:
        list: List of window dictionaries for the room
    """
    rooms = extract_rooms(layout_data)
    
    for room in rooms:
        if room.get('name') == room_name or room.get('id') == room_name:
            return room.get('windows', [])
    
    return []


def print_layout_summary(layout_data):
    """
    Print human-readable summary of layout.
    
    Args:
        layout_data (dict): Parsed layout JSON
    """
    rooms = extract_rooms(layout_data)
    print("=== LAYOUT SUMMARY ===")
    print("Total Rooms: {}".format(len(rooms)))
    print("")
    
    for room in rooms:
        room_name = room.get('name', 'Unnamed')
        room_id = room.get('id', 'No ID')
        windows = room.get('windows', [])
        
        print("Room: {} (ID: {})".format(room_name, room_id))
        print("  Windows: {}".format(len(windows)))
        
        for i, window in enumerate(windows):
            win_width = window.get('width', 'Unknown')
            print("    Window {}: width={}".format(i + 1, win_width))
        print("")


# ============================================================================
# USAGE IN GRASSHOPPER SCRIPT EDITOR
# ============================================================================

if __name__ == '__main__':
    # Set path to your layout.json file
    json_path = r"C:\path\to\layout.json"  # Update this path
    
    # Read layout
    layout = read_layout_json(json_path)
    
    if layout:
        # Print summary
        print_layout_summary(layout)
        
        # Get all rooms
        rooms = extract_rooms(layout)
        print("Rooms found: {}".format([r.get('name') for r in rooms]))
        
        # Get windows for specific room
        room_windows = extract_windows(layout, 'Living Room')
        print("Windows in Living Room: {}".format(room_windows))
        
        # Pass to Grasshopper as output
        # Example: Set 'layout_json' output to json.dumps(layout)
        output = json.dumps(layout)
