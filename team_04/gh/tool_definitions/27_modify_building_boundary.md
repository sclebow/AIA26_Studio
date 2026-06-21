# Tool 27: modify_building_boundary_04

## Category
MANIPULATION TOOLS

## Purpose
Moves, orients, rotates, or mirrors an existing building footprint and reports whether the transformed boundary still fits inside the site.

## MCP Tool Definition

```json
{
  "name": "modify_building_boundary_04",
  "description": "Move, orient, rotate, or mirror an existing building boundary and optionally check whether the transformed footprint still fits inside the site boundary.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "geometry_id": {
        "type": "string"
      },
      "boundary": {
        "type": "array",
        "description": "Closed building footprint polyline as [x, y, z] points",
        "items": {
          "type": "array",
          "items": {"type": "number"},
          "minItems": 3,
          "maxItems": 3
        }
      },
      "target_centroid_xy": {
        "type": "array",
        "items": {"type": "number"},
        "minItems": 2,
        "maxItems": 2
      },
      "translate_by_xy": {
        "type": "array",
        "items": {"type": "number"},
        "minItems": 2,
        "maxItems": 2,
        "default": [0.0, 0.0]
      },
      "rotation_degrees": {
        "type": "number",
        "default": 0.0
      },
      "orientation_degrees": {
        "type": "number",
        "default": 0.0
      },
      "rotation_origin_xy": {
        "type": "array",
        "items": {"type": "number"},
        "minItems": 2,
        "maxItems": 2
      },
      "apply_mirror": {
        "type": "boolean",
        "default": false
      },
      "mirror_axis": {
        "type": "string",
        "enum": ["x", "y"],
        "default": "y"
      },
      "site_boundary": {
        "type": "array",
        "items": {
          "type": "array",
          "items": {"type": "number"},
          "minItems": 3,
          "maxItems": 3
        }
      },
      "clearance": {
        "type": "number",
        "default": 0.0
      }
    },
    "required": ["geometry_id", "boundary"]
  }
}
```

## Output Format

```json
{
  "success": true,
  "data": {
    "geometry_id": "generate_building_boundary_xxx",
    "transformed_boundary": [[x, y, z], [x, y, z]],
    "boundary_area_sqm": 900.0,
    "perimeter_m": 128.0,
    "centroid": [60.0, 40.0, 0.0],
    "bounding_box": {
      "min": [40.0, 20.0, 0.0],
      "max": [80.0, 60.0, 0.0]
    },
    "fits_within_site_boundary": true,
    "boundary_intersects_site_boundary": false,
    "violations": []
  },
  "metadata": {
    "tool_name": "modify_building_boundary_04"
  }
}
```

## Grasshopper Implementation Notes

1. Convert `boundary` into a closed Rhino polyline or curve and compute its centroid.
2. Mirror around `rotation_origin_xy` when supplied, otherwise mirror around the current centroid.
3. Rotate around `rotation_origin_xy` or centroid using `orientation_degrees` first, then `rotation_degrees` when orientation is omitted.
4. Apply either `target_centroid_xy` or `translate_by_xy` to move the footprint.
5. Intersect the transformed boundary against the site boundary and report whether any vertices leave the site or any segments cross the site edge.
6. Return only geometry facts and derived metrics. The Python planner or notebook can decide what to do next.