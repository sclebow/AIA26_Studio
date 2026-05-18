# Tool 25: remaining_buildable_positions_04

## Category
SITE ANALYSIS TOOLS

## Purpose
Pixelizes the remaining site after one or more buildings are placed and returns candidate centroid positions for the next building.

## MCP Tool Definition

```json
{
  "name": "remaining_buildable_positions_04",
  "description": "Pixelize the remaining site and return feasible centroid candidates for the next building.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "site_boundary": {
        "type": "array",
        "items": {
          "type": "array",
          "items": {"type": "number"},
          "minItems": 3,
          "maxItems": 3
        }
      },
      "placed_buildings": {
        "type": "array",
        "description": "Placed building payloads with geometry ids and boundaries"
      },
      "candidate_building_boundary": {
        "type": "array",
        "description": "Optional next building footprint to test at each pixel center",
        "items": {
          "type": "array",
          "items": {"type": "number"},
          "minItems": 3,
          "maxItems": 3
        }
      },
      "grid_size": {
        "type": "number",
        "default": 10.0
      },
      "clearance": {
        "type": "number",
        "default": 0.0
      },
      "max_positions": {
        "type": "integer",
        "default": 100
      }
    },
    "required": ["site_boundary", "placed_buildings"]
  }
}
```

## Output Format

```json
{
  "success": true,
  "data": {
    "candidate_positions": [[x, y, z], [x, y, z]],
    "candidate_count": 24,
    "grid_size": 10.0,
    "clearance": 5.0,
    "site_bounding_box": {
      "min": [0, 0, 0],
      "max": [120, 80, 0]
    },
    "occupied_geometry_ids": ["building_a", "building_b"]
  },
  "metadata": {
    "tool_name": "remaining_buildable_positions_04"
  }
}
```

## Grasshopper Implementation Notes

1. Rasterize or pixelize the site into grid-center points.
2. Remove points outside the site boundary.
3. Remove points blocked by already placed buildings.
4. If `candidate_building_boundary` is supplied, test the full translated footprint, not just the point.
5. Return the surviving candidate points for the LLM to reason over.
