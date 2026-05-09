# Boundary Analyzer Documentation

## Overview
The **Boundary Analyzer** is a local Python tool that analyzes apartment boundary geometries by comparing them against a reference dataset of 25 residential apartment layouts. It provides quantitative scoring and visual SVG output to help identify the best matching apartment types.

### **Key Features**
- ✅ Multi-metric scoring (Area, IoU, Topology)
- ✅ SVG visualization with overlay comparison
- ✅ Self-contained implementation (no external dependencies)
- ✅ Support for complex shapes (L-shaped, T-shaped, rectangular, etc.)
- ✅ Integrated with team_06 agent workflow

---

## How It Works

### **Tool Name**
`boundary_analyzer`

### **Purpose**
Analyzes input boundary geometries against a dataset of 25 residential apartment layouts using three scoring metrics:
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
# Rectangle
python main.py "find matching apartments for boundary: [[0,0], [10,0], [10,7], [0,7], [0,0]]"

# L-shaped
python main.py "analyze L-shaped boundary: [[0,0], [15,0], [15,9], [8,9], [8,14], [0,14], [0,0]]"

# T-shaped
python main.py "boundary: [[0,0], [18,0], [18,5], [11,5], [11,13], [7,13], [7,5], [0,5], [0,0]]"
```

### **Input Parameters**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `input_boundary` | Array of [x,y] coordinates | ✅ Yes | - | Closed-loop boundary coordinates |
| `dataset_path` | String | ❌ No | `assets/boundary_dataset.json` | Path to dataset (relative or absolute) |
| `top_n_results` | Integer | ❌ No | 5 | Number of top matches to return |

**Coordinate Format:**
```python
[[x1, y1], [x2, y2], ..., [xn, yn], [x1, y1]]  # Must close the loop
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
- Requires polygon intersection computation

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
Default weights: `w1=0.2, w2=0.5, w3=0.3` (IoU weighted highest for geometric match)

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
│   │   └── boundary_analyzer.py          # Main tool (402 lines)
│   ├── nodes/
│   │   └── local_tools.py                # Tool registration
│   └── graph.py                          # Routing logic
├── assets/
│   └── boundary_dataset.json             # 25 apartment boundaries
├── output/
│   └── boundary_analysis_*.svg           # Generated visualizations
└── docs/
    └── boundary_analyzer_proposal.md     # This document
```

### **Code Components**

**`boundary_analyzer.py`** contains:
- `get_boundary_analyzer_schema()` - Tool definition for LLM
- `polygon_area()` - Shoelace formula for area calculation
- `polygon_perimeter()` - Perimeter calculation
- `polygon_intersection()` - Sutherland-Hodgman algorithm for IoU
- `calculate_iou()` - Intersection over Union metric
- `calculate_composite_score()` - Weighted scoring
- `generate_svg()` - Visualization generation
- `boundary_analyzer()` - Main entry point

### **Dependencies**
```python
# Use existing dependencies only - NO new packages needed:
# - numpy (already in requirements via torch/sentence-transformers)
# - Built-in: json, math, pathlib

# IoU Implementation:
# - Sutherland-Hodgman algorithm (polygon intersection) - pure Python
# - Shoelace formula (polygon area) - numpy
# - No Shapely required (verified not installed)
```

---

## Dataset

### **Apartment Inventory** (`assets/boundary_dataset.json`)

The dataset contains **25 residential apartment layouts** organized by type:

| Type | Count | IDs | Description |
|------|-------|-----|-------------|
| **Studio** | 3 | apt_001 - apt_003 | Compact, Standard, Large |
| **1-Bedroom** | 4 | apt_004 - apt_007 | Rectangular, L-shaped, Compact, Alcove |
| **2-Bedroom** | 5 | apt_008 - apt_012 | Standard, L-shaped, Wide, T-shaped, Corner |
| **3-Bedroom** | 7 | apt_013 - apt_019 | Compact, Standard, L-shaped, U-shaped, Wide, Stepped, Penthouse |
| **4-Bedroom** | 4 | apt_020 - apt_023 | Compact, Standard, L-shaped, Luxury |
| **Special** | 2 | apt_024 - apt_025 | Split-level 2BR, Duplex 3BR |

### **Dataset Entry Format**
```json
{
  "id": "apt_001",
  "name": "Compact Studio",
  "category": "residential",
  "type": "studio",
  "coordinates": [[0, 0], [7, 0], [7, 6], [0, 6], [0, 0]]
}
```

**Note:** All apartments are purely residential. Coordinates are in meters.

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
│    - Load dataset from assets/boundary_dataset.json         │
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
│ 3. SCORE ALL 25 CANDIDATES                                  │
│    For each apartment in dataset:                           │
│    ├─ Area Score: 1 - |area_diff| / max_area               │
│    ├─ IoU Score: intersection / union (Sutherland-Hodgman) │
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

**1. Dataset Not Found**
```
Error: Dataset not found at team_06/assets/boundary_dataset.json
```
**Solution:** Ensure you're running from `team_06/python` directory or use absolute path.

**2. Invalid Boundary Format**
```
Error: Boundary must be a closed loop
```
**Solution:** Ensure first and last coordinates are identical: `[[0,0], ..., [0,0]]`

**3. No Matches Returned**
```
status: "error", message: "No matches found in dataset"
```
**Solution:** Verify dataset file is valid JSON and contains `boundaries` array.

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

## Summary

**Status:** ✅ Fully Implemented and Tested

**Implementation:**
- 402 lines of self-contained Python code
- Zero external dependencies
- Integrated with team_06 agent workflow
- 25 residential apartment boundaries in dataset

**Performance:**
- < 1 second processing time
- Accurate multi-metric scoring
- SVG visualization generation

**Tested:**
- ✅ Rectangular layouts (perfect match: 1.000)
- ✅ L-shaped apartments (best: 0.826)
- ✅ T-shaped apartments (best: 0.650)
- ✅ Complex multi-vertex boundaries

For questions or issues, refer to the troubleshooting section or check `team_06/python/tools/boundary_analyzer.py` source code.
