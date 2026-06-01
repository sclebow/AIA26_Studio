# Heatmap Integration Guide

## Architecture

```
User Query
    ↓
Graph Workflow (graph.py)
    ↓
OpenCost Database (opencost_database.py)
    ├─ get_cost(item_name) → unit prices
    ├─ get_all_data() → all items
    └─ get_cost_by_category() → category rates
    ↓
Heatmap Generator (heatmap_generator.py)
    ├─ calculate_room_costs() → room prices
    ├─ calculate_openings_costs() → door/window prices
    ├─ calculate_columns_costs() → column prices
    └─ generate_full_heatmap() → complete visualization
    ↓
Heatmap Nodes (heatmap_nodes.py)
    ├─ generate_heatmap_node() → calculate costs
    ├─ present_heatmap_node() → show to user
    └─ calculate_delta_node() → compare scenarios
    ↓
User Response (with cost breakdown + heatmap)
```

---

## File Locations

```
team_05/python/
├── opencost_database.py          ✅ Already exists
├── heatmap_generator.py          ← NEW
├── nodes/
│   ├── heatmap_nodes.py          ← NEW
│   └── tools.py                  ✅ Updated with OpenCost
├── graph.py                       ← NEEDS UPDATE
└── _runtime/
    └── bootstrap.py              ✅ Updated
```

---

## Step 1: Add Files to Your Project

Copy these files to your project:

1. **`heatmap_generator.py`** → `team_05/python/`
2. **`heatmap_nodes.py`** → `team_05/python/nodes/`

---

## Step 2: Update graph.py

Add the heatmap nodes to your workflow. Find the imports section in `graph.py` and add:

```python
from nodes.heatmap_nodes import (
    build_generate_heatmap_node,
    build_present_heatmap_node,
    build_calculate_delta_node
)
```

Then, in your StateGraph builder (where you add other nodes), add:

```python
# Add heatmap nodes to the graph
graph_builder.add_node("generate_heatmap", build_generate_heatmap_node())
graph_builder.add_node("present_heatmap", build_present_heatmap_node())
graph_builder.add_node("calculate_delta", build_calculate_delta_node())
```

Add edges to your routing logic (example):

```python
# Route to heatmap after cost calculation
graph_builder.add_edge("cost_calculation", "generate_heatmap")
graph_builder.add_edge("generate_heatmap", "present_heatmap")
```

---

## Step 3: Update State Definition

Make sure your graph state includes heatmap fields:

```python
@dataclass
class State:
    # ... existing fields ...
    heatmap_data: dict = field(default_factory=dict)
    heatmap_json_string: str = ""
    cost_delta: float = 0.0
    cost_delta_percent: float = 0.0
```

---

## Step 4: Test the Integration

```bash
cd team_05/python
python main.py "calculate cost of 5 wooden doors and show heatmap"
```

---

## How It Works

### 1. OpenCost Database
```python
from opencost_database import get_opencost_db

db = get_opencost_db()
price = db.get_cost("Wooden Door")  # Returns: 350 EUR
```

### 2. Heatmap Generator
```python
from heatmap_generator import get_heatmap_generator

heatmap_gen = get_heatmap_generator()
heatmap = heatmap_gen.generate_full_heatmap(layout_data)
```

Output:
```json
{
  "costs": {
    "rooms": { "room_1": {"total_cost": 28000, ...} },
    "openings": { "doors": {...}, "windows": {...} },
    "totals": {
      "rooms": 200000,
      "doors": 5000,
      "windows": 3000,
      "grand_total": 208000
    }
  },
  "heatmap": {
    "rooms": {
      "room_1": {"heat_t": 0.5, "color_hex": "#FEB24C"}
    }
  }
}
```

### 3. Graph Integration
The workflow:
1. **User asks:** "Calculate cost and show heatmap"
2. **Graph extracts:** rooms, doors, windows, columns
3. **OpenCost queries:** gets live prices for each element
4. **Heatmap generator:** calculates totals and assigns colors
5. **Present node:** shows breakdown to user
6. **Output:** Cost heatmap with visual colors

---

## Data Flow Example

```
Layout Data (JSON)
├─ Rooms: [living, dining, bedroom, kitchen, etc.]
├─ Doors: [front_door, interior_door, etc.]
├─ Windows: [window_1, window_2, etc.]
└─ Columns: [col_1, col_2, etc.]
    ↓
OpenCost Database Queries
├─ get_cost("living") → 3200 EUR/m²
├─ get_cost("wooden door") → 1800 EUR
├─ get_cost("window") → 2800 EUR
└─ get_cost("column") → 1500 EUR
    ↓
Cost Calculations
├─ Living room: 40 m² × 3200 = 128,000 EUR
├─ Doors: 5 × 1800 = 9,000 EUR
├─ Windows: 8 × 2800 = 22,400 EUR
└─ Columns: 9 × 1500 = 13,500 EUR
    ↓
Heatmap Generation
├─ Min cost: 1,500 EUR
├─ Max cost: 128,000 EUR
├─ Color scale: Blue (low) → Red (high)
└─ Room colors: [room_1: #FEB24C, room_2: #BD0026, ...]
    ↓
User Output
├─ Total Cost: 173,000 EUR
├─ Breakdown by type
├─ Visual heatmap with colors
└─ Room-by-room analysis
```

---

## Example Output

When user runs:
```bash
python main.py "calculate building costs with heatmap"
```

The system outputs:

```
## Cost Heatmap Analysis (OpenCost Database)

### Project Overview
- **Total Cost:** 173,000 EUR
- **Currency:** EUR
- **Data Source:** OpenCost

### Cost Breakdown by Element
**Rooms:** 128,000 EUR
**Doors:** 9,000 EUR
**Windows:** 22,400 EUR
**Columns:** 13,500 EUR

### Room-by-Room Breakdown
**Living Room** (ID: living)
- Area: 40 m²
- Unit Rate: 3200 EUR/m²
- Total Cost: 128,000 EUR
- Color: 🟥 Red (high cost)

**Bedroom** (ID: bedroom)
- Area: 22.5 m²
- Unit Rate: 2500 EUR/m²
- Total Cost: 56,250 EUR
- Color: 🟧 Orange (medium-high cost)

[... more rooms ...]
```

---

## Features

✅ **Live OpenCost Integration** - Uses real market data, auto-updated
✅ **Complete Cost Breakdown** - All elements (rooms, doors, windows, columns)
✅ **Visual Heatmap** - Color-coded cost visualization
✅ **Room-by-Room Analysis** - Detailed cost per room
✅ **Trade-off Comparison** - Compare scenarios with delta
✅ **JSON Export** - Save heatmap data for external analysis
✅ **Category Support** - Smart category-based lookups
✅ **Error Handling** - Graceful fallbacks for missing data

---

## Next Steps

1. Copy the files to your project
2. Update graph.py with the imports and nodes
3. Test with: `python main.py "show cost heatmap"`
4. Customize colors and thresholds as needed
5. Integrate with your Grasshopper workflows

---

## Troubleshooting

**Issue:** "No layout data available"
- **Solution:** Make sure layout_data is in the state before heatmap node runs

**Issue:** "OpenCost prices not found"
- **Solution:** Check COST_REGION and COST_CURRENCY in .env

**Issue:** "Heatmap not showing colors"
- **Solution:** Ensure min/max costs are calculated correctly (at least 2 rooms)

---

Everything is connected! 🚀
