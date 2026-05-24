# Tool 5: parametric_shape_generator_04

## Category
SHAPE TOOLS

## Purpose
Creates live, editable parametric building geometry with adjustable parameters (arm length, width, courtyard size, rotation, position).

## MCP Tool Definition

```json
{
  "name": "parametric_shape_generator_04",
  "description": "Creates editable parametric building geometry. Supports bar, L-shape, U-shape, H-shape, courtyard, and cluster configurations.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "shape_base": {
        "type": "string",
        "enum": ["bar", "l_shape", "u_shape", "h_shape", "courtyard", "cluster"],
        "description": "Base building typology"
      },
      "arm_length_m": {
        "type": "number",
        "description": "Length of building arms in meters",
        "default": 60
      },
      "width_m": {
        "type": "number",
        "description": "Width of building bars/corridors in meters",
        "default": 15
      },
      "courtyard_size_m": {
        "type": "number",
        "description": "Internal courtyard dimension in meters (for U/H/courtyard shapes)",
        "default": 30
      },
      "rotation_degrees": {
        "type": "number",
        "description": "Rotation angle in degrees (0-360)",
        "default": 0
      },
      "position_xy": {
        "type": "array",
        "description": "Position [x, y] coordinates for building centroid",
        "items": {"type": "number"},
        "minItems": 2,
        "maxItems": 2,
        "default": [0, 0]
      },
      "floors": {
        "type": "integer",
        "description": "Number of floors",
        "default": 4
      },
      "floor_height_m": {
        "type": "number",
        "description": "Height per floor in meters",
        "default": 3.5
      }
    },
    "required": ["shape_base"]
  }
}
```

## Input Example

```json
{
  "shape_base": "l_shape",
  "arm_length_m": 60,
  "width_m": 15,
  "rotation_degrees": 45,
  "position_xy": [100, 50],
  "floors": 5,
  "floor_height_m": 3.5
}
```

## Output Format

```json
{
  "success": true,
  "data": {
    "geometry_id": "terrapilot_geom_001",
    "live_geometry_guid": "rhino_guid_string",
    "footprint_guid": "rhino_guid_string",
    "footprint_area_sqm": 1350,
    "gfa_sqm": 6750,
    "total_height_m": 17.5,
    "perimeter_m": 150,
    "shape_type": "l_shape",
    "parameters": {
      "arm_length_m": 60,
      "width_m": 15,
      "courtyard_size_m": 0,
      "rotation_degrees": 45,
      "position_xy": [100, 50],
      "floors": 5,
      "floor_height_m": 3.5
    },
    "is_editable": true,
    "bounding_box": {
      "min": [70, 20],
      "max": [130, 80]
    }
  },
  "metadata": {
    "tool_name": "parametric_shape_generator_04",
    "execution_time_ms": 85,
    "timestamp": "2026-05-03T10:35:00Z"
  }
}
```

## Shape Typologies

### 1. Bar
```
┌─────────────────────────┐
│                         │
│        BAR              │
│                         │
└─────────────────────────┘

Parameters: arm_length_m, width_m
```

### 2. L-Shape
```
┌──────────┐
│          │
│          │
│          │
│          └──────────┐
│                     │
│                     │
└─────────────────────┘

Parameters: arm_length_m, width_m, (both arms)
```

### 3. U-Shape
```
┌───┐             ┌───┐
│   │             │   │
│   │             │   │
│   │             │   │
│   └─────────────┘   │
│       COURTYARD     │
└─────────────────────┘

Parameters: arm_length_m, width_m, courtyard_size_m
```

### 4. H-Shape
```
┌───┐             ┌───┐
│   │             │   │
│   ├─────────────┤   │
│   │  CONNECTOR  │   │
│   ├─────────────┤   │
│   │             │   │
└───┘             └───┘

Parameters: arm_length_m, width_m, courtyard_size_m
```

### 5. Courtyard (Full)
```
┌─────────────────────────┐
│                         │
│    ┌─────────────┐      │
│    │             │      │
│    │  COURTYARD  │      │
│    │             │      │
│    └─────────────┘      │
│                         │
└─────────────────────────┘

Parameters: arm_length_m, width_m, courtyard_size_m
```

### 6. Cluster
```
┌────┐    ┌────┐
│    │    │    │
└────┘    └────┘

     ┌────┐
     │    │
     └────┘

Parameters: arm_length_m, width_m, count, spacing
```

## Grasshopper Implementation Steps

### 1. Input Parser (Python Component)
```python
import json

input_data = json.loads(input_json)

# Extract parameters
shape_base = input_data.get("shape_base", "bar")
arm_length = input_data.get("arm_length_m", 60)
width = input_data.get("width_m", 15)
courtyard = input_data.get("courtyard_size_m", 30)
rotation = input_data.get("rotation_degrees", 0)
position = input_data.get("position_xy", [0, 0])
floors = input_data.get("floors", 4)
floor_height = input_data.get("floor_height_m", 3.5)

# Output to grasshopper
a = shape_base
b = arm_length
c = width
d = courtyard
e = rotation
f = position
g = floors
h = floor_height
```

### 2. Shape Generation Logic (Grasshopper)

#### Bar Shape
```
Rectangle component:
  - Length: arm_length_m
  - Width: width_m
  - Plane: World XY at position_xy
  
Extrude:
  - Height: floors * floor_height_m
  
Rotate:
  - Angle: rotation_degrees
  - Center: position_xy
```

#### L-Shape
```
Two Rectangles:
  - Horizontal arm: length x width
  - Vertical arm: length x width
  - Joined at corner
  
Union/Merge regions
Extrude
Rotate
```

#### U-Shape
```
Outer Rectangle:
  - Size: (arm_length + courtyard + width) x arm_length
  
Inner Rectangle (void):
  - Size: courtyard x (arm_length - width)
  
Region Difference (subtract inner from outer)
Extrude
Rotate
```

#### H-Shape
```
Three Rectangles:
  - Left arm: length x width
  - Connector: width x (courtyard + 2*width)
  - Right arm: length x width
  
Union all three
Extrude
Rotate
```

### 3. Parameter Storage
Store parameters in Rhino object UserText:
```python
import scriptcontext as sc
import rhinoscriptsyntax as rs

# After creating geometry
geometry_guid = str(created_geometry.ReferenceID)

# Store parameters as user text
rs.SetUserText(geometry_guid, "geometry_id", "terrapilot_geom_001")
rs.SetUserText(geometry_guid, "shape_base", shape_base)
rs.SetUserText(geometry_guid, "arm_length_m", str(arm_length))
rs.SetUserText(geometry_guid, "width_m", str(width))
# ... etc for all parameters
```

### 4. Output Formatter (Python Component)
```python
import json

# Calculate metrics
footprint_area = calculate_area(footprint_curve)
gfa = footprint_area * floors
total_height = floors * floor_height
perimeter = calculate_perimeter(footprint_curve)

# Generate unique ID
import uuid
geometry_id = f"terrapilot_geom_{str(uuid.uuid4())[:8]}"

output = {
    "success": True,
    "data": {
        "geometry_id": geometry_id,
        "live_geometry_guid": str(geometry_guid),
        "footprint_guid": str(footprint_guid),
        "footprint_area_sqm": float(footprint_area),
        "gfa_sqm": float(gfa),
        "total_height_m": float(total_height),
        "perimeter_m": float(perimeter),
        "shape_type": shape_base,
        "parameters": {
            "arm_length_m": float(arm_length),
            "width_m": float(width),
            "courtyard_size_m": float(courtyard),
            "rotation_degrees": float(rotation),
            "position_xy": position,
            "floors": int(floors),
            "floor_height_m": float(floor_height)
        },
        "is_editable": True,
        "bounding_box": {
            "min": [float(bbox_min.X), float(bbox_min.Y)],
            "max": [float(bbox_max.X), float(bbox_max.Y)]
        }
    },
    "metadata": {
        "tool_name": "parametric_shape_generator_04",
        "execution_time_ms": exec_time,
        "timestamp": timestamp
    }
}

output_json = json.dumps(output, indent=2)
```

## Placeholder Version (Week 1)

```python
import json

input_data = json.loads(input_json) if input_json else {}
shape = input_data.get("shape_base", "bar")
arm_len = input_data.get("arm_length_m", 60)
width = input_data.get("width_m", 15)

# Mock calculations
footprint = arm_len * width
gfa = footprint * 4  # assume 4 floors

output = {
    "success": True,
    "data": {
        "geometry_id": "terrapilot_geom_placeholder_001",
        "live_geometry_guid": "mock-guid-geometry",
        "footprint_guid": "mock-guid-footprint",
        "footprint_area_sqm": footprint,
        "gfa_sqm": gfa,
        "total_height_m": 14.0,
        "perimeter_m": 2 * (arm_len + width),
        "shape_type": shape,
        "parameters": input_data,
        "is_editable": True,
        "bounding_box": {"min": [0, 0], "max": [arm_len, width]}
    },
    "metadata": {
        "tool_name": "parametric_shape_generator_04",
        "execution_time_ms": 15,
        "timestamp": "2026-05-03T10:00:00Z",
        "placeholder": True
    }
}

output_json = json.dumps(output, indent=2)
print(f"parametric_shape_generator_04: PLACEHOLDER - {shape}")
```

## Test Cases

### Test 1: Simple Bar
```json
{
  "shape_base": "bar",
  "arm_length_m": 80,
  "width_m": 12
}
```
Expected: 960 sqm footprint

### Test 2: L-Shape
```json
{
  "shape_base": "l_shape",
  "arm_length_m": 50,
  "width_m": 15,
  "rotation_degrees": 90
}
```
Expected: L-shape rotated 90°

### Test 3: Courtyard Building
```json
{
  "shape_base": "courtyard",
  "arm_length_m": 60,
  "width_m": 15,
  "courtyard_size_m": 30,
  "position_xy": [100, 100],
  "floors": 6
}
```
Expected: Full courtyard building at [100,100]

## Layer Organization

- `TerraPilot_Geometry::Live3D` - 3D building mass
- `TerraPilot_Geometry::Footprints` - 2D footprint curves
- `TerraPilot_Geometry::Parameters` - Text dots showing parameters

## Error Handling

```python
# Validate inputs
if width >= arm_length:
    return {"success": False, "errors": ["Width must be less than arm length"]}

if courtyard_size >= arm_length - 2*width:
    return {"success": False, "errors": ["Courtyard too large for building size"]}

if shape_base not in ["bar", "l_shape", "u_shape", "h_shape", "courtyard", "cluster"]:
    return {"success": False, "errors": [f"Unknown shape type: {shape_base}"]}
```

## Integration Notes

This tool is typically called AFTER Tool 3 (shape_library_loader) or directly if user specifies exact parameters.

The `geometry_id` returned should be stored in agent state and used by all MANIPULATION TOOLS to reference this geometry.

---

**Status:** 🟡 Placeholder Ready → 🟢 Full Implementation (Week 1-2)
