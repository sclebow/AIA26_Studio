# Boundary Analyzer Documentation

## Quick Reference

| Property | Value |
|----------|-------|
| **Tool Name** | `boundary_analyzer` |
| **Type** | Local Python tool (not MCP) |
| **Lines of Code** | 403 (refactored from 529) |
| **Dataset Size** | 30+ residential layouts |
| **MCP Required** | ❌ No - Runs independently |
| **Processing Time** | 0.5-10 seconds (depends on complexity) |
| **Scoring Weights** | Area: 20%, IoU: 50%, Topology: 30% |
| **Rotation Testing** | 0°, 90°, 180°, 270° |
| **Grid Resolution** | 100×100 samples |
| **Output** | JSON + SVG visualization |

**Quick Start:**
```bash
cd team_06/python
python main.py "analyze boundary: [[0,0], [12,0], [12,8], [0,8], [0,0]]"
```

---

## Overview
The **Boundary Analyzer** is a local Python tool that analyzes apartment boundary geometries by comparing them against a reference dataset of 30+ residential apartment layouts from `sample_layouts.json`. It provides quantitative scoring and visual SVG output to help identify the best matching apartment types.

**⚡ Runs independently without MCP server** - The tool works as a standalone Python application and does not require Rhino/Grasshopper to be running.

### **Key Features**
- ✅ Multi-metric scoring (Area, IoU, Topology)
- ✅ **Rotation-invariant IoU** - Tests 0°, 90°, 180°, 270° orientations
- ✅ **Grid-based sampling** - Accurate IoU for concave polygons (L, T, U shapes)
- ✅ **Dual input modes** - Direct coordinates or load from layout JSON file
- ✅ SVG visualization with overlay comparison
- ✅ Self-contained implementation (no external dependencies)
- ✅ Support for complex shapes (L-shaped, T-shaped, irregular stepped boundaries)
- ✅ Integrated with team_06 agent workflow
- ✅ Modular SVG utilities (reusable by other tools)
- ✅ **MCP-optional bootstrap** - Works with or without MCP server connection

---

## How It Works

### **Tool Name**
`boundary_analyzer`

### **Purpose**
Analyzes input boundary geometries against a dataset of 30+ residential apartment layouts using three scoring metrics:
1. **Area Similarity** - Compares total floor area
2. **IoU (Intersection over Union)** - Measures geometric overlap
3. **Topology Score** - Evaluates shape characteristics (vertices, perimeter, compactness)

---

## Usage

### **Calling the Tool via Agent**

From the `team_06/python` directory:

```bash
python main.py "analyze this apartment boundary: [[0,0], [12,0], [12,8], [0,8], [0,0]]"
```

### **Natural Language Examples**

```bash
# Using input layout file (recommended)
python main.py "analyze the boundary from team_06_input_layout.json"

# Using direct coordinates - Rectangle
python main.py "find matching apartments for boundary: [[0,0], [10,0], [10,7], [0,7], [0,0]]"

# L-shaped
python main.py "analyze L-shaped boundary: [[0,0], [15,0], [15,9], [8,9], [8,14], [0,14], [0,0]]"

# T-shaped
python main.py "boundary: [[0,0], [18,0], [18,5], [11,5], [11,13], [7,13], [7,5], [0,5], [0,0]]"

# Irregular stepped boundary
python main.py "analyze boundary: [[0,0], [15,0], [15,4], [10,4], [10,8], [18,8], [18,12], [8,12], [8,16], [0,16], [0,0]]"
```

### **Input Parameters**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `input_boundary` | Array of [x,y] coordinates | ⚠️ Optional* | - | Closed-loop boundary coordinates |
| `input_layout_path` | String | ⚠️ Optional* | `team_06_input_layout.json` | Path to input layout JSON (uses `outline` field) |
| `dataset_path` | String | ❌ No | `layout_inputs/sample_layouts.json` | Path to dataset (relative or absolute) |
| `top_n_results` | Integer | ❌ No | 5 | Number of top matches to return |

**\*Note:** Either `input_boundary` OR `input_layout_path` must be provided.

**Coordinate Format:**
```python
[[x1, y1], [x2, y2], ..., [xn, yn], [x1, y1]]  # Must close the loop
```

**Input Layout File Format:**
```json
{
  "layoutId": "Layout-001",
  "apartment": {...},
  "outline": [
    [-3.86, -3.36],
    [-3.86, 3.36],
    [3.86, 3.36],
    [3.86, -3.36],
    [-3.86, -3.36]
  ]
}
```

---

## Scoring Methodology

### **1. Area Similarity Score (0-1)**
```
area_score = 1 - |area_input - area_candidate| / max(area_input, area_candidate)
```

### **2. IoU (Intersection over Union) Score (0-1)**
```
IoU = intersection_area / union_area
```
- Measures geometric overlap/recall
- **Rotation-invariant**: Tests 4 orientations (0°, 90°, 180°, 270°) and returns best match
- **Grid-based sampling**: Uses 100×100 grid with point-in-polygon algorithm
- **Handles concave polygons**: Unlike Sutherland-Hodgman, works correctly for L/T/U shapes
- **Normalization**: Both polygons translated to origin before comparison

### **3. Boundary Topology Score (0-1)**
Composite of:
- **Vertex count similarity**: `1 - |vertices_input - vertices_candidate| / max(vertices_input, vertices_candidate)`
- **Perimeter ratio**: `1 - |perimeter_input - perimeter_candidate| / max(perimeter_input, perimeter_candidate)`
- **Compactness similarity**: Compare `4π × area / perimeter²`

```
topology_score = (vertex_similarity + perimeter_similarity + compactness_similarity) / 3
```

### **4. Composite Score**
```
composite_score = (w1 × area_score) + (w2 × IoU_score) + (w3 × topology_score)
```
**Configurable weights** (defined as constants):
```python
WEIGHT_AREA = 0.2      # 20% - Area similarity
WEIGHT_IOU = 0.5       # 50% - Geometric overlap (highest weight)
WEIGHT_TOPOLOGY = 0.3  # 30% - Shape characteristics
```
IoU weighted highest for geometric match accuracy.

---

## Output Format

### **JSON Response**
```json
{
    "status": "success",
    "input_boundary_stats": {
        "area": 1250.5,
        "perimeter": 145.2,
        "vertex_count": 8,
        "compactness": 0.745
    },
    "top_matches": [
        {
            "rank": 1,
            "boundary_id": "boundary_042",
            "composite_score": 0.89,
            "area_score": 0.95,
            "iou_score": 0.87,
            "topology_score": 0.88,
            "metadata": {
                "name": "L-shaped apartment",
                "category": "residential"
            }
        }
    ],
    "visualization_svg": "<svg>...</svg>",
    "output_file": "team_06/output/boundary_analysis_<timestamp>.svg"
}
```

### **SVG Visualization Layout**
```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  ┌──────────────────────┐  ┌─────────────────────────┐ │
│  │                      │  │  ANALYSIS RESULTS       │ │
│  │   Input Boundary     │  │                         │ │
│  │   (Blue outline)     │  │  Match: boundary_042    │ │
│  │                      │  │  Composite: 0.89        │ │
│  │   Best Match         │  │                         │ │
│  │   (Red outline)      │  │  Area Score:    0.95    │ │
│  │                      │  │  IoU Score:     0.87    │ │
│  │   Overlap            │  │  Topology Score: 0.88   │ │
│  │   (Purple fill)      │  │                         │ │
│  │                      │  │  Input Stats:           │ │
│  │                      │  │  - Area: 1250.5         │ │
│  └──────────────────────┘  │  - Perimeter: 145.2     │ │
│                            │  - Vertices: 8          │ │
│                            │                         │ │
│                            │  Match Stats:           │ │
│                            │  - Area: 1198.3         │ │
│                            │  - Perimeter: 142.8     │ │
│                            │  - Vertices: 8          │ │
│                            └─────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Architecture

### **File Structure**
```
team_06/
├── python/
│   ├── tools/
│   │   └── boundary_analyzer.py          # Main tool (393 lines, refactored)
│   ├── utils/
│   │   ├── __init__.py                   # Utils package exports
│   │   └── svg_utils.py                  # Reusable SVG generation
│   ├── nodes/
│   │   └── local_tools.py                # Tool registration
│   └── graph.py                          # Routing logic
├── layout_inputs/
│   └── sample_layouts.json               # 30+ residential layouts
├── output/
│   └── boundary_analysis_*.svg           # Generated visualizations
└── docs/
    ├── boundary_analyzer.md              # This document
    ├── boundary_analyzer_refactoring.md  # Refactoring summary
    └── boundary_analyzer_rotation_fix.md # Rotation invariance fix
```

### **Code Components**

**`boundary_analyzer.py`** (403 lines) contains:

**Constants Section:**
- `WEIGHT_AREA`, `WEIGHT_IOU`, `WEIGHT_TOPOLOGY` - Scoring weights
- `GRID_RESOLUTION` - Grid sampling density (100×100)
- `ROTATION_ANGLES` - Angles to test [0, 90, 180, 270]
- `DEFAULT_TOP_N` - Default number of results (5)

**Tool Schema:**
- `get_boundary_analyzer_schema()` - Tool definition for LLM

**Geometry Utilities:**
- `polygon_area()` - Shoelace formula for area calculation
- `polygon_perimeter()` - Perimeter calculation
- `polygon_compactness()` - Shape compactness metric
- `get_bounding_box()` - Extract min/max x/y coordinates
- `normalize_to_origin()` - Translate polygon to (0,0)
- `rotate_polygon()` - Rotate around centroid
- `point_in_polygon()` - Ray casting algorithm

**IoU Calculation:**
- `calculate_iou_grid()` - Grid-based sampling for concave polygons
- `calculate_iou_with_rotation()` - Rotation-invariant IoU (tests 4 angles)

**Scoring Functions:**
- `calculate_area_score()` - Area similarity
- `calculate_topology_score()` - Vertex/perimeter/compactness similarity
- `calculate_composite_score()` - Weighted combination
- `compute_boundary_stats()` - Extract all polygon statistics

**Main Entry Point:**
- `boundary_analyzer()` - Main tool function

**`utils/svg_utils.py`** (reusable module):
- `generate_boundary_comparison_svg()` - Create comparison visualization
- `create_polygon_path()` - Convert coordinates to SVG path
- `transform_coords_to_viewport()` - Scale/translate for viewport

### **Dependencies**
```python
# Use existing dependencies only - NO new packages needed:
# - numpy (already in requirements via torch/sentence-transformers)
# - Built-in: json, math, pathlib, datetime, typing

# IoU Implementation:
# - Grid-based sampling with point-in-polygon (ray casting)
# - Shoelace formula (polygon area) - numpy
# - Rotation matrices - numpy
# - No Shapely required (verified not installed)
```

### **Code Quality Improvements**

**Refactoring (May 2026):**
- ✅ Removed 3 unused functions (51 lines saved)
  - Deleted `calculate_iou()` (Sutherland-Hodgman based)
  - Deleted `polygon_intersection()` (fails on concave polygons)
  - Deleted `clip_polygon_component()` (helper for above)
- ✅ Extracted `get_bounding_box()` helper (eliminates 3 duplications)
- ✅ Centralized configuration as constants
- ✅ Extracted SVG generation to reusable `utils/svg_utils.py`
- ✅ Improved documentation and function docstrings
- ✅ **Result:** 9.6% code reduction, better maintainability

---

## Dataset

### **Layout Inventory** (`layout_inputs/sample_layouts.json`)

The dataset contains **30+ residential apartment layouts** with detailed geometry information.

### **Dataset Entry Format**
```json
{
  "layoutId": "layout-1",
  "apartment": {
    "id": "layout-1",
    "name": "Sample A",
    "geometry": [...],
    "attributes": {
      "area": 32.47
    }
  },
  "outline": [
    [-3.088, -2.628],
    [-3.088, 2.628],
    [3.088, 2.628],
    [3.088, -2.628],
    [-3.088, -2.628]
  ]
}
```

**Key Fields:**
- `layoutId`: Unique identifier for the layout
- `apartment.name`: Descriptive name (e.g., "Sample A", "Sample B")
- `apartment.attributes.area`: Pre-calculated area
- `outline`: **Boundary coordinates used for matching** (closed-loop polygon)

**Note:** The tool uses the `outline` field for boundary comparison. All coordinates are in meters.

---

## Running Without MCP Server

### **MCP-Optional Bootstrap**

The boundary analyzer runs as a **local Python tool** and does not require the MCP server (Rhino/Grasshopper) to be running. The bootstrap process gracefully handles MCP unavailability:

```python
# _runtime/bootstrap.py
try:
    mcp_client.initialize()
    tools = mcp_client.list_tools()
    print(f"[bootstrap] Discovered MCP tools: {mcp_tool_names}")
except Exception as e:
    print(f"[bootstrap] Warning: Could not connect to MCP server: {type(e).__name__}")
    print(f"[bootstrap] Continuing with local tools only...")
```

**Expected Output:**
```
[bootstrap] Loaded layout: input_layout (team_06_input_layout.json)
[bootstrap] Warning: Could not connect to MCP server: ConnectError
[bootstrap] Continuing with local tools only...
[bootstrap] Discovered local tools: ['boundary_analyzer', 'layout_filter', 'layout_graph_search']
[bootstrap] Total tools available: 3
```

**Benefits:**
- ✅ Faster development and testing
- ✅ No dependency on Rhino/Grasshopper for boundary analysis
- ✅ Graceful degradation when MCP unavailable
- ✅ Full functionality for local tools

---

## Integration

### **Agent Workflow Integration**

The tool is registered as a **local tool** (not MCP) for faster execution:

**1. Tool Registration** (`nodes/local_tools.py`)
```python
from tools.boundary_analyzer import boundary_analyzer, get_boundary_analyzer_schema

def get_local_tools():
    return [
        get_boundary_analyzer_schema(),  # Registered here
        # ... other local tools
    ]
```

**2. Routing Logic** (`graph.py`)
```python
def _route(state: AgentState) -> str:
    if state["pending_tool_calls"]:
        for call in state["pending_tool_calls"]:
            if call["name"] in ["boundary_analyzer", ...]:
                return "local_tool"  # Routes to local execution
    return "run_tool"  # MCP tools
```

**3. Execution** (`nodes/local_tools.py`)
```python
if tool_name == "boundary_analyzer":
    tool_output = boundary_analyzer(
        input_boundary=tool_args.get("input_boundary"),
        dataset_path=tool_args.get("dataset_path"),
        top_n_results=tool_args.get("top_n_results", 5)
    )
```

---

## Processing Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. INPUT VALIDATION                                         │
│    - Verify closed-loop coordinates                         │
│    - Load dataset from layout_inputs/sample_layouts.json         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. COMPUTE INPUT STATS                                      │
│    - Area (Shoelace formula)                                │
│    - Perimeter (Euclidean distances)                        │
│    - Vertex count                                           │
│    - Compactness (4π × area / perimeter²)                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. SCORE ALL CANDIDATES                                     │
│    For each apartment in dataset:                           │
│    ├─ Area Score: 1 - |area_diff| / max_area               │
│    ├─ IoU Score: Rotation-invariant grid-based sampling    │
│    │   • Normalize both polygons to origin                  │
│    │   • Test 4 rotations (0°, 90°, 180°, 270°)            │
│    │   • Sample 100×100 grid with point-in-polygon         │
│    │   • Return best IoU across rotations                   │
│    ├─ Topology: (vertex_sim + perim_sim + compact_sim) / 3 │
│    └─ Composite: 0.2×area + 0.5×IoU + 0.3×topology         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. RANK & SELECT TOP N                                      │
│    - Sort by composite_score (descending)                   │
│    - Return top 5 matches (default)                         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. GENERATE SVG VISUALIZATION                               │
│    - Overlay input (blue) + best match (red)                │
│    - Analysis panel with scores and stats                   │
│    - Save to team_06/output/boundary_analysis_<timestamp>   │
└─────────────────────────────────────────────────────────────┘
```

---

## Example Results

### **Test Case 1: Perfect Rectangle Match**

**Input:**
```python
[[0,0], [12,0], [12,8], [0,8], [0,0]]  # 12×8 rectangle
```

**Output:**
```json
{
  "status": "success",
  "input_boundary_stats": {
    "area": 96.0,
    "perimeter": 40.0,
    "vertex_count": 4,
    "compactness": 0.754
  },
  "top_matches": [
    {
      "rank": 1,
      "boundary_id": "apt_004",
      "name": "Rectangular 1BR",
      "composite_score": 1.000,  // Perfect match!
      "area_score": 1.000,
      "iou_score": 1.000,
      "topology_score": 1.000
    }
  ],
  "output_file": "team_06/output/boundary_analysis_20260509_064311.svg"
}
```

### **Test Case 2: L-Shaped Apartment**

**Input:**
```python
[[0,0], [15,0], [15,9], [8,9], [8,14], [0,14], [0,0]]
```

**Best Match:** `apt_013` - Compact 3BR
- Composite: 0.826
- Area: 0.994 (175.0 vs 176.0)
- IoU: 0.755
- Topology: 0.831

### **Test Case 3: T-Shaped Apartment**

**Input:**
```python
[[0,0], [18,0], [18,5], [11,5], [11,13], [7,13], [7,5], [0,5], [0,0]]
```

**Best Match:** `apt_010` - Wide 2BR
- Composite: 0.650
- Area: 0.847 (122.0 vs 144.0)
- IoU: 0.565
- Topology: 0.660

---

## Performance

### **Metrics**
- **Processing Time:** < 1 second for 25 boundaries
- **Accuracy:** IoU calculation using Sutherland-Hodgman algorithm
- **Score Range:** All metrics normalized to 0-1
- **Output Size:** SVG files ~5-8 KB

### **Tested Scenarios**
✅ Rectangular apartments (studios, 1BR, 2BR, 3BR, 4BR)
✅ L-shaped layouts (1BR, 2BR, 3BR, 4BR)
✅ T-shaped layouts (2BR)
✅ U-shaped layouts (3BR)
✅ Complex multi-vertex boundaries (8+ vertices)
✅ Perfect matches (score = 1.000)
✅ Partial matches (score 0.5 - 0.9)

---

## Troubleshooting

### **Common Issues**

**1. MCP Server Connection Warning (Normal)**
```
[bootstrap] Warning: Could not connect to MCP server: ConnectError
[bootstrap] Continuing with local tools only...
```
**Solution:** This is **normal** if Rhino/Grasshopper is not running. The boundary analyzer will work fine with local tools only.

**2. Dataset Not Found**
```
Error: Dataset not found at team_06/layout_inputs/sample_layouts.json
```
**Solution:** Ensure you're running from `team_06/python` directory or use absolute path.

**3. Invalid Boundary Format**
```
Error: Boundary must be a closed loop
```
**Solution:** Ensure first and last coordinates are identical: `[[0,0], ..., [0,0]]`

**4. No Matches Returned**
```
status: "error", message: "No matches found in dataset"
```
**Solution:** Verify dataset file is valid JSON array with layouts containing `outline` field.

**5. ModuleNotFoundError: No module named 'dotenv'**
```
ModuleNotFoundError: No module named 'dotenv'
```
**Solution:** Activate the virtual environment before running:
```powershell
& E:\softwares-4\AIA26_Studio\.venv\Scripts\Activate.ps1
```

### **Debug Mode**

Enable debug output in `main.py`:
```python
DEBUG_GRAPH="true"  # In .env file
```

This will print:
- Tool calls and arguments
- Scoring results for each candidate
- SVG generation status

---

## Technical Details

### **Dependencies**
- **numpy** - Already installed via `torch`/`sentence-transformers`
- **Built-in modules:** `json`, `math`, `pathlib`, `datetime`, `typing`
- **No external packages required**

### **Algorithms Used**

**Sutherland-Hodgman Polygon Clipping** (IoU calculation)
- Clips subject polygon against each edge of clip polygon
- Handles convex and simple concave polygons
- Time complexity: O(n×m) where n,m are vertex counts

**Shoelace Formula** (Area calculation)
```python
area = 0.5 × |Σ(x_i × y_{i+1} - x_{i+1} × y_i)|
```

**Compactness Metric**
```python
compactness = 4π × area / perimeter²
```
- Circle = 1.0 (most compact)
- Square ≈ 0.785
- Complex shapes < 0.5

---

## Future Enhancements

### **Planned**
- [ ] Expand dataset to 50+ apartment types
- [ ] Add rotation-invariant matching
- [ ] Support for multi-polygon boundaries (apartments with courtyards)
- [ ] Export to PDF/PNG formats

### **Possible**
- [ ] Machine learning-based similarity scoring
- [ ] Interactive SVG with clickable match exploration
- [ ] Real-time boundary editing and re-analysis
- [ ] Integration with Grasshopper for 3D extrusion

---

## Performance & Testing

### **Computational Complexity**

**Per Boundary Comparison:**
- **Grid-based IoU**: 100×100 = 10,000 point-in-polygon checks
- **Rotation testing**: 4 orientations × 10,000 samples = 40,000 checks
- **Total for 30+ layouts**: ~1.2 million point-in-polygon operations

**Processing Time:**
- Simple shapes (4-6 vertices): ~0.5-1 second
- Complex shapes (8-10 vertices): ~2-5 seconds
- Irregular boundaries (10+ vertices): ~5-10 seconds

**Optimization Opportunities:**
- Reduce `GRID_RESOLUTION` from 100 to 50 (4x faster, slight accuracy loss)
- Reduce rotation angles to [0, 90] for orthogonal-only shapes
- Early termination if IoU > 0.95 found

### **Test Results**

**Rectangular Boundaries:**
- ✅ Perfect match: Composite score 1.000
- ✅ Correct identification of apt_004 (Rectangular 1BR)

**L-shaped Boundaries:**
- ✅ Rotation-invariant: Horizontal and vertical L-shapes both match apt_005
- ✅ Perfect match: Composite score 1.000
- ✅ IoU correctly handles concave geometry

**T-shaped Boundaries:**
- ✅ Correct match: apt_011 (T-shaped 2BR)
- ✅ Composite score: 1.000

**Irregular Stepped Boundaries (10 vertices):**
- ✅ Best match: apt_018 (Stepped 3BR)
- ✅ Composite score: 0.767
- ✅ Area score: 0.953, IoU: 0.730, Topology: 0.705

---

## Configuration Tuning

All configuration constants are defined at the top of `boundary_analyzer.py`:

```python
# Scoring weights (must sum to 1.0)
WEIGHT_AREA = 0.2       # Adjust to prioritize area matching
WEIGHT_IOU = 0.5        # Adjust to prioritize geometric overlap
WEIGHT_TOPOLOGY = 0.3   # Adjust to prioritize shape characteristics

# Grid-based IoU sampling resolution
GRID_RESOLUTION = 100   # Higher = more accurate but slower (50-200 recommended)

# Rotation angles to test (degrees)
ROTATION_ANGLES = [0, 90, 180, 270]  # Reduce to [0, 90] for faster processing

# Default number of top matches to return
DEFAULT_TOP_N = 5       # Increase to see more candidates
```

**Tuning Recommendations:**

| Use Case | Suggested Changes |
|----------|-------------------|
| **Faster processing** | `GRID_RESOLUTION = 50`, `ROTATION_ANGLES = [0, 90]` |
| **Higher accuracy** | `GRID_RESOLUTION = 150`, keep all 4 rotations |
| **Prioritize exact size** | `WEIGHT_AREA = 0.4`, `WEIGHT_IOU = 0.4`, `WEIGHT_TOPOLOGY = 0.2` |
| **Prioritize shape** | `WEIGHT_AREA = 0.1`, `WEIGHT_IOU = 0.6`, `WEIGHT_TOPOLOGY = 0.3` |
| **More results** | `DEFAULT_TOP_N = 10` |

---

## Summary

**Status:** ✅ Fully Implemented, Refactored, and Tested

**Implementation:**
- **Modular design**: SVG utilities extracted to `utils/svg_utils.py`
- **MCP-optional**: Runs independently without Rhino/Grasshopper
- **Dual input modes**: Direct coordinates or load from layout JSON file
- Zero external dependencies (uses existing numpy)
- Integrated with team_06 agent workflow
- 30+ residential apartment layouts in dataset (`sample_layouts.json`)

**Key Features:**
- ✅ **Rotation-invariant IoU** (tests 4 orientations)
- ✅ **Grid-based sampling** (handles concave polygons)
- ✅ **Configurable constants** (easy tuning)
- ✅ **Reusable SVG utilities** (for other tools)
- ✅ **Standalone operation** (no MCP server required)

**Tested Shapes:**
- ✅ Rectangles (perfect match: 1.000)
- ✅ L-shaped (rotation-invariant: 1.000)
- ✅ T-shaped (perfect match: 1.000)
- ✅ Irregular stepped boundaries (best: 0.767)
- ✅ T-shaped apartments (best: 0.650)
- ✅ Complex multi-vertex boundaries

For questions or issues, refer to the troubleshooting section or check `team_06/python/tools/boundary_analyzer.py` source code.