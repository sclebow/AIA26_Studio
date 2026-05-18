"""
Layout Filter Tool.

Returns dicts for direct Python function calls.
"""

import json

# ---------------------------------------------------------------------------
# Load JSON from string for backward compatibility with old state format
# ---------------------------------------------------------------------------
def load_json_from_string(json_string):
    try:
        data = json.loads(json_string)
    except Exception as e:
        raise ValueError(f"Invalid JSON string: {e}")
    return data

# ---------------------------------------------------------------------------
# Select layout by id.
# Note: can be extended to support other criteria like area or room_summary search.
# Returns dict with matching layout or error dict
# ---------------------------------------------------------------------------
def select_layout(all_layouts, layout_id=None):
    # Handle if all_layouts is a string (for backward compatibility)
    if isinstance(all_layouts, str):
        layouts_list = load_json_from_string(all_layouts)
    else:
        layouts_list = all_layouts
    
    try:
        # Check which parameter is not empty and use it
        if layout_id:  # Check if not None and not empty string
            result = _search_by_layout_id(layouts_list, layout_id)
        else:
            # All inputs empty
            result = None
        
        # Return dict directly
        if result is None:
            return {"error": "No layout found matching criteria"}
        return result
    
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Search by layoutId (exact match)
# ---------------------------------------------------------------------------
def _search_by_layout_id(layouts_list, layout_id):
    for layout in layouts_list:
        if isinstance(layout, str):
            try:
                layout = json.loads(layout)
            except:
                continue
        
        if layout.get("layoutId") == layout_id:
            return layout
    
    return None
