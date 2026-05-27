# Tool 1: site_boundary_reader_04

## Category
INPUT TOOLS

## Purpose
Reads site vertex list/coordinates and generates site boundary geometry with analysis metrics.

## MCP Tool Definition

```json
{
  "name": "site_boundary_reader_04",
  "description": "Reads site boundary coordinates and generates site geometry with area calculations. Can optionally place trees on site.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "polygon_coordinates": {
        "type": "array",
        "description": "Array of [x, y] coordinate pairs defining the site boundary polygon",
        "items": {
          "type": "array",
          "items": {"type": "number"},
          "minItems": 2,
          "maxItems": 2
        }
      },
      "site_area_sqm": {
        "type": "number",
        "description": "Optional: Site area in square meters for validation"
      },
      "number_of_trees": {
        "type": "integer",
        "description": "Optional: Number of protected trees to place on site"
      },
      "tree_radius_m": {
        "type": "number",
        "description": "Optional: Protection radius for each tree in meters",
        "default": 5
      }
    },
    "required": ["polygon_coordinates"]
  }
}
```

## Input Example

```json
{
  "polygon_coordinates": [
    [0, 145.1],
    [-140.9, 75.6],
    [-108.5, -112.4],
    [108.5, -112.4],
    [140.9, 75.6]
  ],
  "site_area_sqm": 50000,
  "number_of_trees": 80,
  "tree_radius_m": 5
}
```

## Output Format

```json
{
  "success": true,
  "data": {
    "site_boundary_curve": "rhino_guid_string",
    "site_area_sqm": 49856.3,
    "site_centroid": [0, 0],
    "bounding_box": {
      "min": [-140.9, -112.4],
      "max": [140.9, 145.1]
    },
    "perimeter_m": 856.4,
    "number_of_sides": 5,
    "tree_circles": ["guid1", "guid2", "..."],
    "tree_locations": [[x1, y1], [x2, y2], "..."],
    "usable_area_sqm": 46858.2
  },
  "metadata": {
    "tool_name": "site_boundary_reader_04",
    "execution_time_ms": 45,
    "timestamp": "2026-05-03T10:30:00Z"
  }
}
```

## Grasshopper Implementation Steps

### 1. Input Parser (Python Component)
```python
import json

# Parse input JSON
input_data = json.loads(input_json)

# Extract coordinates
coords = input_data.get("polygon_coordinates", [])
tree_count = input_data.get("number_of_trees", 0)
tree_radius = input_data.get("tree_radius_m", 5)

# Output to grasshopper
a = coords  # Will be used to create polyline
b = tree_count
c = tree_radius
```

### 2. Geometry Creation (Grasshopper Components)
- **Point List**: Convert coordinate pairs to Rhino points
- **Polyline**: Create polyline from points
- **Close Curve**: Ensure polygon is closed
- **Planar Surface**: Create surface from closed curve
- **Area**: Calculate area
- **Centroid**: Find center point
- **Bounding Box**: Get min/max extents

### 3. Tree Placement (Optional, if tree_count > 0)
- **Random Points**: Generate random points in boundary
- **Circle**: Create circles with tree_radius
- **Cull Pattern**: Remove circles that overlap boundary edge

### 4. Output Formatter (Python Component)
```python
import json
import System

# Collect geometry GUIDs
boundary_guid = str(boundary_curve.ReferenceID) if boundary_curve else None
tree_guids = [str(c.ReferenceID) for c in tree_circles] if tree_circles else []

# Format output
output = {
    "success": True,
    "data": {
        "site_boundary_curve": boundary_guid,
        "site_area_sqm": float(area),
        "site_centroid": [float(centroid.X), float(centroid.Y)],
        "bounding_box": {
            "min": [float(bbox_min.X), float(bbox_min.Y)],
            "max": [float(bbox_max.X), float(bbox_max.Y)]
        },
        "perimeter_m": float(perimeter),
        "number_of_sides": int(num_sides),
        "tree_circles": tree_guids,
        "tree_locations": [[float(p.X), float(p.Y)] for p in tree_points],
        "usable_area_sqm": float(usable_area)
    },
    "metadata": {
        "tool_name": "site_boundary_reader_04",
        "execution_time_ms": int(exec_time),
        "timestamp": timestamp_string
    }
}

output_json = json.dumps(output, indent=2)
```

## Placeholder Version (Week 1)

```python
import json

# Parse input
input_data = json.loads(input_json) if input_json else {}
coords = input_data.get("polygon_coordinates", [[0,0], [100,0], [100,100], [0,100]])

# Mock output
output = {
    "success": True,
    "data": {
        "site_boundary_curve": "mock-guid-001",
        "site_area_sqm": 10000,
        "site_centroid": [50, 50],
        "bounding_box": {"min": [0, 0], "max": [100, 100]},
        "perimeter_m": 400,
        "number_of_sides": len(coords),
        "tree_circles": [],
        "tree_locations": [],
        "usable_area_sqm": 10000
    },
    "metadata": {
        "tool_name": "site_boundary_reader_04",
        "execution_time_ms": 10,
        "timestamp": "2026-05-03T10:00:00Z",
        "placeholder": True
    }
}

output_json = json.dumps(output, indent=2)
print("site_boundary_reader_04: PLACEHOLDER MODE")
print(f"Received {len(coords)} coordinate pairs")
```

## Test Cases

### Test 1: Simple Rectangle
```json
{
  "polygon_coordinates": [[0,0], [100,0], [100,80], [0,80]]
}
```
Expected: 8000 sqm, 4 sides

### Test 2: Pentagon (from slides)
```json
{
  "polygon_coordinates": [
    [0, 145.1],
    [-140.9, 75.6],
    [-108.5, -112.4],
    [108.5, -112.4],
    [140.9, 75.6]
  ],
  "site_area_sqm": 50000,
  "number_of_trees": 80,
  "tree_radius_m": 5
}
```
Expected: ~50000 sqm, 5 sides, 80 tree circles

### Test 3: Irregular
```json
{
  "polygon_coordinates": [
    [0,0], [120,10], [140,50], [100,120], [20,100], [-10,40]
  ]
}
```
Expected: Irregular polygon, area calculated

## Layer Organization

Bake geometry to layers:
- `TerraPilot_Input::SiteBoundary` - Site boundary curve
- `TerraPilot_Input::Trees` - Tree protection circles
- `TerraPilot_Input::Analysis` - Helper geometry (centroid, bbox, etc.)

## Error Handling

```python
try:
    # Main logic
    result = calculate_site_metrics(coords)
    output = {"success": True, "data": result}
except ValueError as e:
    output = {
        "success": False,
        "errors": [f"Invalid coordinates: {str(e)}"],
        "data": None
    }
except Exception as e:
    output = {
        "success": False,
        "errors": [f"Unexpected error: {str(e)}"],
        "data": None
    }
```

## Integration Notes

This tool is typically called FIRST in any TerraPilot workflow. The output provides the site boundary that all other tools reference.

The `site_boundary_curve` GUID should be stored in the agent state and passed to subsequent tools that need site context.

## Dependencies

- Rhino.Geometry (built-in)
- Python JSON library (built-in)

## Performance

Expected execution time: < 100ms for typical sites with < 100 trees

---

**Status:** 🟡 Placeholder Ready → 🟢 Full Implementation (Week 1)
