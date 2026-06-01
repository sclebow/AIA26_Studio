# Tool 26: requested_position_checker_04

## Category
SITE ANALYSIS TOOLS

## Purpose
Checks whether a user-requested point can host the proposed building footprint and returns geometric reasons plus nearby feasible alternatives.

## MCP Tool Definition

```json
{
  "name": "requested_position_checker_04",
  "description": "Check whether a user-requested point can host the proposed building and suggest nearby feasible positions.",
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
        "type": "array"
      },
      "proposed_boundary": {
        "type": "array",
        "items": {
          "type": "array",
          "items": {"type": "number"},
          "minItems": 3,
          "maxItems": 3
        }
      },
      "requested_point": {
        "type": "array",
        "items": {"type": "number"},
        "minItems": 2,
        "maxItems": 2
      },
      "candidate_positions": {
        "type": "array"
      },
      "clearance": {
        "type": "number",
        "default": 0.0
      },
      "max_suggestions": {
        "type": "integer",
        "default": 5
      }
    },
    "required": ["site_boundary", "placed_buildings", "proposed_boundary", "requested_point"]
  }
}
```

## Output Format

```json
{
  "success": true,
  "data": {
    "requested_point": [70, 25, 0],
    "is_feasible": false,
    "geometric_reasons": [
      "Building footprint overlaps placed building 1."
    ],
    "suggested_positions": [[80, 25, 0], [90, 25, 0]],
    "translated_boundary": [[x, y, z], [x, y, z]]
  },
  "metadata": {
    "tool_name": "requested_position_checker_04"
  }
}
```

## Grasshopper Implementation Notes

1. Translate the proposed footprint so its centroid lands on `requested_point`.
2. Check whether the full translated footprint stays inside the site.
3. Check collisions and clearance against existing buildings.
4. Return geometry facts only. The LLM should combine those facts with the user narrative and architectural intent.
5. If infeasible, rank nearby feasible points and return them as suggestions.
