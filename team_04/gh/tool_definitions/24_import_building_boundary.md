# Tool 24: import_building_boundary_04

## Category
PLACEMENT TOOLS

## Purpose
Creates Rhino or Grasshopper geometry from a Python-generated closed building footprint boundary so the agent can place each building one by one.

## MCP Tool Definition

```json
{
  "name": "import_building_boundary_04",
  "description": "Create Rhino/Grasshopper geometry from a Python-generated closed building boundary.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "geometry_id": {
        "type": "string",
        "description": "Stable id from the Python generator"
      },
      "boundary": {
        "type": "array",
        "description": "Closed footprint polyline as [x, y, z] points",
        "items": {
          "type": "array",
          "items": {"type": "number"},
          "minItems": 3,
          "maxItems": 3
        }
      },
      "layer_name": {
        "type": "string",
        "default": "TerraPilot_Output::BuildingFootprint"
      },
      "closed": {
        "type": "boolean",
        "default": true
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
    "footprint_guid": "rhino_guid_string",
    "layer_name": "TerraPilot_Output::BuildingFootprint",
    "is_closed": true,
    "point_count": 5
  },
  "metadata": {
    "tool_name": "import_building_boundary_04"
  }
}
```

## Grasshopper Implementation Notes

1. Parse `boundary` JSON into Rhino points.
2. Create a polyline and ensure it is closed.
3. Convert to a curve if needed for downstream tools.
4. Bake or reference it on the target layer.
5. Return the Rhino GUID so later tools can refer to the placed building.
