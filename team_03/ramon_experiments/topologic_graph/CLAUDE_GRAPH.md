# Building Layout Graph Analysis System

## Overview

A comprehensive Python-based system for analyzing building layout JSON files and generating network graphs with spatial relationship analysis. The system detects all building elements (rooms, doors, windows, furniture, MEP systems, walls, etc.) and creates relationship networks with visualization and data export capabilities.

---

## Objectives

1. **Visualize building layouts** as interactive network graphs showing element relationships
2. **Discover relationships** between building elements through:
   - ID references in attributes
   - Spatial proximity analysis
   - Containment relationships (roomId)
   - System groupings
   - Functional connections (doors connecting rooms)
3. **Normalize and quantify** spatial relationships
4. **Calculate space syntax metrics** for network analysis
5. **Export data** as PNG visualizations and CSV files for further analysis

---

## System Architecture

### Core Components

#### 1. **JSON Parsing Engine** (`load_and_analyze_layout`)
- Dynamically detects all categories in input JSON
- Extracts element properties: ID, name, geometry, attributes
- Calculates geometric centers and bounding boxes
- Builds initial node set with category-based coloring

**Category Color Mapping:**
```
Rooms       → Red (#FF6B6B)
Doors       → Teal (#4ECDC4)
Windows     → Light Blue (#45B7D1)
Furniture   → Light Orange (#FFA07A)
MEP Systems → Purple (#DDA0DD)
Walls       → Gray (#A9A9A9)
Structure   → Gray (#A9A9A9)
Outline     → Gold (#FFD700)
```

#### 2. **Relationship Discovery Engine** (6-step process)

**Step 1: ID Reference Relationships**
- Scans all element attributes for string/list values
- Creates edges when attribute values match element IDs
- Relationship type: `references`
- Weight: 1.0 (string) or 0.9 (list items)

**Step 2: Spatial Proximity Analysis**
- Calculates Euclidean distance between all element centers
- Threshold: 15.0 units
- Normalizes distances using min-max scaling (0-1 range)
- Strength calculated as: `1.0 - normalized_distance`
- Relationship type: `spatial_near`

**Step 3: Containment Relationships**
- Detects `roomId` attributes in element definitions
- Creates edges from element to containing room
- Relationship type: `contained_in`
- Weight: 1.0

**Step 4: System-Based Relationships**
- Groups elements by matching `system` attributes
- Creates edges between elements in same system
- Relationship type: `system_group`
- Weight: 0.8

**Step 5: Functional Relationships**
- Identifies doors with `connectsRooms` arrays
- Creates edges between connected rooms
- Relationship type: `door_connection`
- Weight: 1.0

#### 3. **Space Syntax Metrics** (`calculate_space_syntax_metrics`)

For each node, calculates:
- **Degree Centrality**: Local importance (connections / total_nodes-1)
- **Betweenness Centrality**: Bridge role in network
- **Closeness Centrality**: Average distance to all other nodes
- **Eigenvector Centrality**: Influence based on connected node importance

#### 4. **Visualization Engine** (`visualize_comprehensive_graph`)

**Graph Layout:**
- Algorithm: Spring Layout (NetworkX)
- Parameters: k=2, iterations=100, seed=42
- Figure size: 26x20 inches at 300 DPI

**Node Rendering:**
- Color: Mapped from element category via hex-to-RGB conversion
- Size: 1000 + (degree/max_degree × 5000) — scales by connectivity
- Edge color: Black, linewidth 2
- Alpha: 0.85 (semi-transparent)

**Edge Rendering by Relationship Type:**
```
References           → Blue (#4169E1), solid, linewidth 1.5, alpha 0.5
Spatial Proximity    → Green (#32CD32), dotted (:), linewidth 1, alpha 0.3
Contained In         → Red (#FF6B6B), dash-dot (-.), linewidth 2, alpha 0.6
System Group         → Purple (#9932CC), dashed (--), linewidth 1.5, alpha 0.5
Door Connection      → Orange (#FF4500), solid, linewidth 3, alpha 0.8
```

**Labels:**
- Displayed for rooms, doors, and high-degree nodes (≥3 connections)
- Font size: 9, bold weight

**Legend:**
- 6 element type patches
- 5 relationship type line styles
- Position: Upper left
- Background: Transparent frame

**Statistics Box:**
- Elements, Nodes, Edges counts
- Network Density
- Position: Lower right
- Background: Wheat colored

#### 5. **Data Export Engine** (`export_csv`)

**nodes.csv** - Node metrics
- Columns: Node_ID, Name, Type, Center_X, Center_Y, Width, Height, Degree, Degree_Centrality, Betweenness_Centrality, Closeness_Centrality, Eigenvector_Centrality, Attributes

**edges.csv** - Relationship data
- Columns: Source, Target, Relationship_Type, Attribute, Distance, Normalized_Distance, Weight

**metrics_summary.csv** - Aggregate statistics
- Total element/node/relationship counts
- Breakdown by element type
- Breakdown by relationship type

---

## Technical Implementation

### Key Algorithms

**Distance Normalization:**
```python
normalized_distance = (distance - min_distance) / (max_distance - min_distance)
proximity_strength = 1.0 - normalized_distance
```

**Color Conversion:**
```python
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4))
```

**Node Sizing by Importance:**
```python
max_degree = max(dict(G.degree()).values())
size = 1000 + (degree / max_degree * 5000)
```

### Graph Properties

- **Type**: Undirected (nx.Graph)
- **Multi-edges**: Allowed (same element pair may have multiple relationship types)
- **Self-loops**: Excluded
- **Attributes per edge**: relationship type, attribute name, distance, normalized distance, weight

---

## Results Analysis

### Layout Comparison

| Layout | Elements | Relationships | Network Density | Connectivity Type |
|--------|----------|---------------|-----------------|-------------------|
| industrial_01 | 22 | 221 | 0.866 | Highly interconnected |
| industrial_005 | 45 | 406 | ~0.356 | Sparse |
| residential_02 | 43 | 907 | 0.961 | Very dense |
| residential_03 | 56 | 1,387 | 0.868 | Highly dense |

**Key Insights:**
- Residential layouts show much higher connectivity (0.86-0.96) vs industrial (0.36-0.87)
- residential_02 most densely connected despite similar element count to industrial_005
- Higher density indicates tighter spatial/functional relationships
- Industrial layouts tend toward fewer but more specialized relationships

---

## Generated Outputs

### File Naming Convention
All exports follow pattern: `{layout_name}_{output_type}`

### Output Files per Layout

1. **{layoutname}_comprehensive.png** (5-15 MB)
   - Full network visualization
   - All nodes, edges, labels, legends, statistics
   - 26x20 inch canvas
   - 300 DPI resolution

2. **{layoutname}_nodes.csv** (5-10 KB)
   - One row per node
   - Complete metric data
   - Geometry information

3. **{layoutname}_edges.csv** (20-70 KB)
   - One row per relationship
   - Normalized distance values
   - Relationship type classification

4. **{layoutname}_metrics_summary.csv** (0.3-1 KB)
   - Aggregate statistics
   - Type breakdowns
   - Network properties

---

## Usage

### Basic Execution

```python
python layout_graph_generator.py
```

### Changing Target Layout

Edit line 569 in layout_graph_generator.py:
```python
json_path = r"c:\Users\User\Desktop\00-MaCAD\GitHub\AIAStudio_test\Layouts\{layout_name}.json"
```

### Supported Layouts

- industrial_01.json ✓
- industrial_02.json
- industrial_03.json
- industrial_005.json ✓
- residential_02.json ✓
- residential_03.json ✓

---

## Dependencies

- **networkx** 3.2 — Graph creation and algorithms
- **matplotlib** 3.8.2 — Visualization rendering
- **numpy** — Numerical operations
- **json** — Data parsing (built-in)
- **csv** — Data export (built-in)
- **os, math** — Utilities (built-in)

### Installation

```bash
pip install networkx==3.2 matplotlib==3.8.2 numpy
```

---

## Troubleshooting

### Color Display Issues
- **Problem**: Nodes displaying in gray despite color configuration
- **Solution**: Ensure hex colors are converted to RGB tuples via `hex_to_rgb()` before passing to matplotlib

### Missing Categories
- **Problem**: Elements from certain category types not appearing
- **Solution**: Add category name variants to `base_colors` dict (e.g., both 'room' and 'rooms')

### Low Visualization Quality
- **Solution**: Increase figure size or DPI in `visualize_comprehensive_graph()`

---

## Performance Notes

- **Graph Generation**: ~1-2 seconds for 40-50 elements
- **Visualization**: ~5-10 seconds (depends on edge count)
- **CSV Export**: <1 second
- **Memory Usage**: ~50-100 MB for typical layouts

---

## Future Enhancements

1. Interactive visualization (Plotly, Pyvis)
2. 3D graph rendering with Z-axis layout
3. Spatial clustering analysis
4. Room connectivity matrices
5. Path analysis (shortest path between spaces)
6. Centrality-based ranking visualization
7. Hierarchical layout for clarity
8. Real-time filtering by relationship type

---

## Version History

- **v1.0** - Initial release
  - 6-step relationship discovery
  - Space syntax metrics
  - Comprehensive visualization
  - CSV export
  - Multi-layout support
  - Color-coded nodes by element type
  - Edge styling by relationship type

---

## Author Notes

This system was developed to provide comprehensive spatial and relational analysis of building layouts in JSON format. The multi-perspective relationship discovery approach reveals both explicit (referenced IDs, systems) and implicit (spatial proximity) connections between building elements. The resulting network graphs and exported data enable further analysis in specialized tools like Gephi, Cytoscape, or custom analytics pipelines.

The color scheme and relationship styling follow common architectural visualization conventions, with warm colors for primary spaces (rooms) and cool colors for connective/functional elements (doors, windows).
