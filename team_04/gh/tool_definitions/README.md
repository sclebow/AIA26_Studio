# Grasshopper Tool Template

## Overview
This directory contains detailed specifications for each of the 23 TerraPilot tools.

Each tool should follow this structure in Grasshopper:

```
┌─────────────────────────────────────────┐
│  MCP TOOL WRAPPER (Cluster Input)       │
│  • Receives JSON string input           │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  JSON PARSER                            │
│  • Parse input JSON                     │
│  • Extract parameters                   │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  CORE LOGIC (Grasshopper components)    │
│  • Actual geometric operations          │
│  • Calculations                         │
│  • Validations                          │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  OUTPUT FORMATTER                       │
│  • Collect results                      │
│  • Format as JSON                       │
│  • Add metadata                         │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  MCP TOOL OUTPUT (Cluster Output)       │
│  • Returns JSON string                  │
└─────────────────────────────────────────┘
```

## Python Component Template

For JSON parsing and formatting, use Python components in Grasshopper:

```python
# INPUT PARSER (Python component at start of cluster)
import json
import System

# Get input string
json_input = input_json  # This comes from cluster input

# Parse JSON
try:
    data = json.loads(json_input)
    # Extract specific parameters
    param1 = data.get("param1", default_value)
    param2 = data.get("param2", default_value)
    # Output to grasshopper
    a = param1  # Connect to rest of grasshopper
    b = param2
except Exception as e:
    error = str(e)
```

```python
# OUTPUT FORMATTER (Python component at end of cluster)
import json

# Collect results from grasshopper components
result_data = {
    "success": True,
    "output1": output1,  # From grasshopper
    "output2": output2,
    "metadata": {
        "tool_name": "tool_name_04",
        "timestamp": "2026-05-03T10:00:00Z"
    }
}

# Format as JSON
output_json = json.dumps(result_data, indent=2)
```

## Placeholder Implementation

For initial development, each tool should have a minimal working version:

```python
# PLACEHOLDER TEMPLATE
import json

input_data = json.loads(input_json) if input_json else {}

# Mock output for testing
output = {
    "success": True,
    "message": f"Tool {tool_name} executed successfully",
    "input_received": input_data,
    "placeholder": True,
    "note": "This is a placeholder implementation"
}

output_json = json.dumps(output, indent=2)
print(f"{tool_name} called with: {input_data}")
```

## Testing Each Tool

Test JSON for each tool:

1. **Create test_inputs.json** with sample data
2. **Connect to MCP server** via Python agent
3. **Call tool** and verify output
4. **Iterate** until working correctly

## Tool Naming Convention

All tools must follow the pattern: `{description}_{team_number}`

Example:
- `site_boundary_reader_04`
- `parametric_shape_generator_04`
- `courtyard_modifier_tool_04`

## Input/Output Standards

### Input Format (always JSON string)
```json
{
  "parameter_name": value,
  "another_parameter": value
}
```

### Output Format (always JSON string)
```json
{
  "success": true/false,
  "data": {
    "result_field_1": value,
    "result_field_2": value
  },
  "geometry_guid": "optional-rhino-guid",
  "errors": ["optional", "error", "messages"],
  "metadata": {
    "tool_name": "tool_name_04",
    "execution_time_ms": 123,
    "timestamp": "ISO-8601-string"
  }
}
```

## Error Handling

All tools should gracefully handle errors:

```python
try:
    # Main logic here
    result = {"success": True, "data": calculated_data}
except Exception as e:
    result = {
        "success": False,
        "errors": [str(e)],
        "data": None
    }

output_json = json.dumps(result, indent=2)
```

## Grasshopper Component Suggestions

### For Site/Boundary Tools
- Polyline component
- Boundary Surfaces
- Area component
- Point List

### For Constraint Checking
- Curve Proximity
- Point In Curve (containment)
- Region Intersection
- Distance calculations

### For Geometry Manipulation
- Scale
- Rotate
- Move
- Transform
- Split
- Offset

### For Evaluation
- Ladybug (sun analysis)
- Area calculations
- Distance measurements
- Boolean operations

## Next Steps

1. Start with Tool 1 (site_boundary_reader_04)
2. Create placeholder that accepts JSON and returns JSON
3. Test MCP connection from Python
4. Implement actual logic
5. Move to Tool 2, repeat

---

**Remember:** DRY but runnable! Each tool should do something, even if it's just echoing back the input with a success message.
