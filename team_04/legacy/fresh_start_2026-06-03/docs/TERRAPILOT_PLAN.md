# TerraPilot - Detailed Implementation Plan
## Team 04 - AI Site & Building Optimization System

---

## 📋 Executive Summary

**Project Goal:** Create an AI system that selects the best building shape and site placement based on constraints, where "the site argues back and the building responds with decisions."

**Core Philosophy:** Buildings should consciously:
- Align with something
- Ignore something
- Resist something
- Frame something
- Avoid something

**Inspiration:** Spacemaker by Autodesk

---

## 🎯 System Architecture Overview

```
User Natural Language Prompt
         ↓
LLM Understands Goal
         ↓
Calls MCP Tools (Grasshopper)
         ↓
Grasshopper Generates/Modifies Geometry
         ↓
Baked Geometry + ID
         ↓
Returns Results to User + Explanation
```

---

## 🛠️ Complete Tool Stack (23 Tools)

### 📥 **INPUT TOOLS** (2 tools)

#### Tool 1: `site_boundary_reader_04`
**Purpose:** Reads site vertex list/coordinates

**Inputs:**
- Polygon coordinates (array of [x, y] points)
- Optional: site_area (float, square meters)
- Optional: number_of_trees (int)
- Optional: tree_radius_m (float)

**Outputs:**
- `site_boundary`: Closed polyline curve in Rhino
- `site_area_sqm`: Calculated site area
- `site_centroid`: Center point [x, y]
- `bounding_box`: Min/max coordinates

**GH Implementation Notes:**
```
Input: JSON string with polygon coordinates
Process: 
  1. Parse JSON coordinates
  2. Create polyline from points
  3. Close curve
  4. Calculate area
  5. Generate tree circles if specified
Output: Geometry + metrics as JSON
```

**Test Case:**
```json
{
  "polygon_coordinates": [
    [0, 145.1],
    [-140.9, 75.6],
    [-108.5, -112.4],
    [108.5, -112.4],
    [140.9, 75.6]
  ],
  "site_area_sqm": 50000,
  "number_of_trees": 80,
  "tree_radius_m": 5
}
```

---

#### Tool 2: `context_reader_04`
**Purpose:** Reads surrounding context objects

**Inputs:**
- `roads`: Array of polyline coordinates
- `neighboring_buildings`: Array of building footprints (polygons)
- `entrances`: Array of point coordinates
- `view_directions`: Array of important view vectors

**Outputs:**
- Context geometry baked to Rhino layers:
  - Layer: `TerraPilot_Context_Roads`
  - Layer: `TerraPilot_Context_Buildings`
  - Layer: `TerraPilot_Context_Entrances`
- `context_summary`: JSON with distances, orientations

**GH Implementation Notes:**
```
Input: JSON with context objects
Process:
  1. Parse each context type
  2. Create geometry
  3. Organize by layer
  4. Calculate proximity metrics
Output: Baked geometry + analysis JSON
```

---

### 🏗️ **SHAPE TOOLS** (3 tools)

#### Tool 3: `shape_library_loader_04`
**Purpose:** Loads predefined building typologies

**Available Shapes:**
- `bar`: Simple linear bar
- `l_shape`: L-configuration
- `u_shape`: U-configuration with courtyard
- `h_shape`: Double bar with connector
- `courtyard`: Full courtyard enclosure
- `cluster`: Multiple connected volumes

**Inputs:**
- `shape_type`: String (one of above)
- `base_width_m`: Float (default: 15)
- `base_length_m`: Float (default: 60)
- `floors`: Int (default: 4)
- `floor_height_m`: Float (default: 3.5)

**Outputs:**
- `building_geometry`: 3D mass model
- `footprint_area_sqm`: Ground floor area
- `gfa_sqm`: Gross floor area
- `shape_parameters`: Editable parameter set

**GH Implementation Notes:**
```
Input: Shape type + dimensions
Process:
  1. Load parametric template for shape type
  2. Apply input dimensions
  3. Generate 3D geometry
  4. Calculate areas
Output: Geometry + parameter JSON
```

---

#### Tool 4: `legal_constraints_reader_04`
**Purpose:** Reads and validates legal/zoning constraints

**Inputs:**
- `site_coverage_max`: Float (0.0 to 1.0, e.g., 0.4 = 40%)
- `setback_north_m`: Float
- `setback_south_m`: Float
- `setback_east_m`: Float
- `setback_west_m`: Float
- `max_height_m`: Float
- `far_max`: Float (Floor Area Ratio)

**Outputs:**
- `buildable_area`: Polygon showing legal build zone
- `constraint_summary`: JSON with all limits
- `violations`: Array of constraint violations (if any)

**GH Implementation Notes:**
```
Input: Legal parameters
Process:
  1. Create setback offset from site boundary
  2. Calculate buildable envelope
  3. Visualize constraint zones
Output: Geometry + validation JSON
```

---

#### Tool 5: `parametric_shape_generator_04`
**Purpose:** Creates live, editable building geometry

**Inputs:**
- `shape_base`: String (from Tool 3)
- `arm_length_m`: Float (for L/U/H shapes)
- `width_m`: Float (corridor width)
- `courtyard_size_m`: Float (internal void dimension)
- `rotation_degrees`: Float (0-360)
- `position_xy`: [x, y] coordinates

**Outputs:**
- `live_geometry`: Parametric 3D model
- `parameter_handles`: JSON of adjustable parameters
- `geometry_id`: Unique identifier

**GH Implementation Notes:**
```
Input: Shape parameters
Process:
  1. Generate parametric grasshopper definition
  2. Create editable sliders/parameters
  3. Link to geometry outputs
Output: Live geometry + parameter control JSON
```

---

### ✅ **CONSTRAINT TOOLS** (5 tools)

#### Tool 6: `site_fit_checker_04`
**Purpose:** Validates if building fits within site boundary

**Inputs:**
- `building_footprint`: Polygon coordinates
- `site_boundary`: Polygon coordinates

**Outputs:**
- `fits`: Boolean (true/false)
- `overlap_area_sqm`: Float (if overlapping)
- `distance_to_boundary_m`: Minimum clearance
- `violation_points`: Array of coordinates outside boundary

**GH Implementation Notes:**
```
Input: Building + site polygons
Process:
  1. Check polygon containment
  2. Calculate overlaps
  3. Find minimum distances
Output: Boolean + metrics JSON
```

---

#### Tool 7: `setback_checker_04`
**Purpose:** Validates legal setback distances

**Inputs:**
- `building_footprint`: Polygon
- `site_boundary`: Polygon
- `required_setbacks`: {north, south, east, west} in meters

**Outputs:**
- `compliant`: Boolean
- `violations`: Array of {edge, required, actual, deficit}
- `setback_zones`: Visualization geometry

**GH Implementation Notes:**
```
Input: Building + setback requirements
Process:
  1. Offset site boundary inward by setbacks
  2. Check if building is inside offset
  3. Measure actual clearances
Output: Compliance boolean + violation details
```

---

#### Tool 8: `area_requirement_checker_04`
**Purpose:** Validates program area requirements

**Inputs:**
- `required_gfa_sqm`: Float (total gross floor area needed)
- `required_footprint_sqm`: Float (ground floor area needed)
- `actual_gfa_sqm`: Float (from current design)
- `actual_footprint_sqm`: Float (from current design)

**Outputs:**
- `gfa_compliant`: Boolean
- `footprint_compliant`: Boolean
- `gfa_surplus_deficit_sqm`: Float (positive = surplus, negative = deficit)
- `footprint_surplus_deficit_sqm`: Float

**GH Implementation Notes:**
```
Input: Required vs actual areas
Process:
  1. Compare values
  2. Calculate differences
  3. Determine compliance
Output: Boolean + delta metrics JSON
```

---

#### Tool 9: `adjacency_access_checker_04`
**Purpose:** Validates access to roads and entrances

**Inputs:**
- `building_footprint`: Polygon
- `road_centerlines`: Array of polylines
- `entrance_points`: Array of [x, y] points
- `min_distance_to_road_m`: Float (required)
- `max_distance_to_entrance_m`: Float (required)

**Outputs:**
- `road_access_ok`: Boolean
- `entrance_access_ok`: Boolean
- `nearest_road_distance_m`: Float
- `nearest_entrance_distance_m`: Float
- `access_routes`: Geometry showing connections

**GH Implementation Notes:**
```
Input: Building + context + distance requirements
Process:
  1. Find closest road point
  2. Find closest entrance
  3. Measure distances
  4. Check against requirements
Output: Boolean + distance metrics + path geometry
```

---

#### Tool 10: `tree_constraint_checker_04`
**Purpose:** Validates building doesn't conflict with protected trees

**Inputs:**
- `building_footprint`: Polygon
- `tree_locations`: Array of [x, y] points
- `tree_radius_m`: Float (protection zone)
- `tree_ids`: Array of tree identifiers

**Outputs:**
- `no_conflicts`: Boolean
- `conflicting_trees`: Array of tree IDs that overlap
- `conflict_areas`: Geometry showing overlaps
- `nearest_tree_distance_m`: Float

**GH Implementation Notes:**
```
Input: Building + tree data
Process:
  1. Create buffer circles around trees
  2. Check intersection with building
  3. List conflicts
Output: Boolean + conflict details JSON
```

---

### 🔧 **MANIPULATION TOOLS** (7 tools)

#### Tool 11: `scale_shape_tool_04`
**Purpose:** Scale, offset, or split building mass

**Operations:**
- `scale_uniform`: Increase/decrease all dimensions
- `offset_from_boundary`: Pull form inward from site edge
- `split_into_wings`: Break mass into two separate bars

**Inputs:**
- `geometry_id`: String (from Tool 5)
- `operation`: String (see above)
- `scale_factor`: Float (e.g., 1.2 = 120% size)
- `offset_distance_m`: Float (for offset operation)
- `split_axis`: String ("x" or "y", for split operation)

**Outputs:**
- `modified_geometry`: Updated 3D model
- `new_footprint_area_sqm`: Float
- `transformation_description`: String

**GH Implementation Notes:**
```
Input: Geometry ID + operation parameters
Process:
  1. Retrieve geometry by ID
  2. Apply transformation
  3. Update parameters
  4. Recalculate metrics
Output: New geometry + updated metrics JSON
```

---

#### Tool 12: `stretch_arm_tool_04`
**Purpose:** Lengthen one wing of L/U/H shapes

**Inputs:**
- `geometry_id`: String
- `arm_identifier`: String ("north", "south", "east", "west")
- `extension_m`: Float (distance to extend)

**Outputs:**
- `modified_geometry`: Updated 3D model
- `new_arm_length_m`: Float
- `added_gfa_sqm`: Float

**GH Implementation Notes:**
```
Input: Geometry ID + arm + extension
Process:
  1. Identify target arm
  2. Extend geometry along arm axis
  3. Update parameters
Output: Modified geometry + metrics JSON
```

---

#### Tool 13: `width_modifier_tool_04`
**Purpose:** Change corridor or bar thickness

**Inputs:**
- `geometry_id`: String
- `new_width_m`: Float
- `which_wing`: String ("all", "north", "south", "east", "west")

**Outputs:**
- `modified_geometry`: Updated 3D model
- `new_gfa_sqm`: Float
- `width_change_m`: Float (delta)

**GH Implementation Notes:**
```
Input: Geometry ID + width parameters
Process:
  1. Adjust perpendicular dimension of bar(s)
  2. Maintain corner connections
  3. Update all parameters
Output: Modified geometry + metrics JSON
```

---

#### Tool 14: `courtyard_modifier_tool_04`
**Purpose:** Increase or reduce central void (carve operation)

**Inputs:**
- `geometry_id`: String
- `courtyard_dimension_m`: Float (square courtyard side length)
- `courtyard_offset_from_center_xy`: [x, y] (optional)

**Outputs:**
- `modified_geometry`: Updated 3D model with void
- `courtyard_area_sqm`: Float
- `remaining_gfa_sqm`: Float

**GH Implementation Notes:**
```
Input: Geometry ID + courtyard size
Process:
  1. Create void region
  2. Subtract from building mass
  3. Maintain structural logic
Output: Modified geometry + metrics JSON
```

---

#### Tool 15: `rotate_mirror_tool_04`
**Purpose:** Rotate or mirror shape for optimal orientation

**Inputs:**
- `geometry_id`: String
- `operation`: String ("rotate" or "mirror")
- `rotation_degrees`: Float (for rotate)
- `mirror_axis`: String ("x" or "y", for mirror)
- `rotation_center_xy`: [x, y] (optional, default = centroid)

**Outputs:**
- `modified_geometry`: Updated 3D model
- `new_orientation_degrees`: Float
- `optimal_sun_exposure`: Boolean

**GH Implementation Notes:**
```
Input: Geometry ID + transformation
Process:
  1. Apply rotation or mirror transformation
  2. Update position data
  3. Recalculate sun analysis
Output: Modified geometry + orientation JSON
```

---

#### Tool 16: `bend_angle_tool_04`
**Purpose:** Bend or angle wings to respond to irregular boundaries

**Inputs:**
- `geometry_id`: String
- `bend_point_distance_m`: Float (from origin)
- `bend_angle_degrees`: Float (-90 to +90)
- `which_wing`: String ("north", "south", "east", "west")

**Outputs:**
- `modified_geometry`: Updated 3D model with bend
- `geometry_is_valid`: Boolean
- `new_footprint_area_sqm`: Float

**GH Implementation Notes:**
```
Input: Geometry ID + bend parameters
Process:
  1. Identify bend location on wing
  2. Apply angular transformation
  3. Validate geometry integrity
Output: Modified geometry + validation JSON
```

---

#### Tool 17: `terrace_step_tool_04`
**Purpose:** Create stepped terraces for slope adaptation

**Inputs:**
- `geometry_id`: String
- `terrain_slope_degrees`: Float
- `terrace_count`: Int (number of steps)
- `step_height_m`: Float

**Outputs:**
- `modified_geometry`: Updated 3D model with terraces
- `total_height_variation_m`: Float
- `cut_fill_volumes_m3`: {cut, fill} volumes

**GH Implementation Notes:**
```
Input: Geometry ID + terrain parameters
Process:
  1. Divide building into terrace zones
  2. Step floors based on slope
  3. Calculate earthwork
Output: Modified geometry + terrain adaptation JSON
```

---

### 🧠 **REASONING TOOLS** (1 tool)

#### Tool 18: `why_operation_selector_04`
**Purpose:** LLM-driven operation selection based on narrative intent

**This is a PYTHON-SIDE tool, not a Grasshopper tool**

**Inputs:**
- `user_narrative`: String (e.g., "Need courtyard light")
- `site_conditions`: JSON (from input tools)
- `current_design_state`: JSON (from shape tools)
- `available_operations`: Array of operation names

**Outputs:**
- `recommended_operation`: String (tool name)
- `operation_parameters`: JSON (suggested parameter values)
- `reasoning`: String (explanation of why this operation)

**Implementation Notes:**
```python
# This is handled by the LLM in the reason node
# System prompt should include operation mapping:
# "courtyard light" -> courtyard_modifier_tool_04
# "frame plaza" -> split or rotate
# "align street" -> rotate_mirror_tool_04
# "maximize views" -> rotate_mirror_tool_04
# "respond to slope" -> terrace_step_tool_04
```

**Example Mappings:**
```
Need courtyard light → courtyard_modifier_tool_04
Need frame plaza → scale_shape_tool_04 (split operation)
Need align street → rotate_mirror_tool_04
Need more area → scale_shape_tool_04 or stretch_arm_tool_04
Respond to slope → terrace_step_tool_04
Irregular boundary → bend_angle_tool_04
```

---

### 📊 **EVALUATION TOOLS** (3 tools)

#### Tool 19: `spatial_intention_evaluator_04`
**Purpose:** Evaluate if design meets spatial goals

**Evaluation Criteria:**
- Does it frame plaza?
- Does it avoid noise?
- Does it open to view?
- Does it protect privacy?

**Inputs:**
- `building_footprint`: Polygon
- `plaza_location`: [x, y] (if applicable)
- `noise_sources`: Array of [x, y] points
- `view_directions`: Array of vectors
- `privacy_zones`: Array of sensitive areas

**Outputs:**
- `frames_plaza`: Boolean + quality score (0-1)
- `avoids_noise`: Boolean + noise exposure score (0-1)
- `opens_to_view`: Boolean + view score (0-1)
- `protects_privacy`: Boolean + privacy score (0-1)
- `overall_spatial_score`: Float (0-1)

**GH Implementation Notes:**
```
Input: Building + spatial criteria
Process:
  1. Analyze geometry orientation
  2. Check adjacencies to key features
  3. Calculate exposure/protection metrics
Output: Boolean checks + scores JSON
```

---

#### Tool 20: `performance_evaluator_04`
**Purpose:** Quantitative performance metrics

**Metrics:**
- Sun exposure (hours of direct sun)
- Open space percentage
- Slope adaptation quality
- Access quality
- Area efficiency

**Inputs:**
- `building_geometry`: 3D model
- `site_boundary`: Polygon
- `latitude`: Float (for sun calc)
- `analysis_date`: String ("summer_solstice", "winter_solstice", "equinox")

**Outputs:**
- `sun_hours_avg`: Float (average across facades)
- `open_space_percentage`: Float (0-100)
- `slope_adaptation_score`: Float (0-1)
- `access_score`: Float (0-1)
- `area_efficiency_ratio`: Float (usable/gross area)
- `overall_performance_score`: Float (0-1)

**GH Implementation Notes:**
```
Input: Building + site + analysis parameters
Process:
  1. Run Ladybug sun analysis
  2. Calculate open space ratio
  3. Evaluate access paths
  4. Compute efficiency metrics
Output: Comprehensive performance JSON
```

---

#### Tool 21: `shape_integrity_evaluator_04`
**Purpose:** Validate design integrity and buildability

**Checks:**
- Circulation possible?
- Proportions reasonable?
- Still recognizable as intended typology?
- Structural feasibility?

**Inputs:**
- `building_geometry`: 3D model
- `original_shape_type`: String (from Tool 3)
- `min_corridor_width_m`: Float (default: 2.5)
- `max_wing_length_m`: Float (default: 80)

**Outputs:**
- `circulation_viable`: Boolean
- `proportions_reasonable`: Boolean
- `typology_recognizable`: Boolean
- `structurally_feasible`: Boolean
- `integrity_issues`: Array of problem descriptions
- `overall_integrity_score`: Float (0-1)

**GH Implementation Notes:**
```
Input: Building + validation criteria
Process:
  1. Check circulation paths exist
  2. Validate dimension ratios
  3. Compare to original typology
  4. Flag structural concerns
Output: Boolean checks + issues JSON
```

---

### 📤 **OUTPUT TOOLS** (2 tools)

#### Tool 22: `bake_geometry_id_04`
**Purpose:** Permanently store geometry in Rhino with unique ID

**Inputs:**
- `geometry_id`: String (from parametric tools)
- `layer_name`: String (optional, default: "TerraPilot_Output")
- `color_rgb`: [r, g, b] (optional)
- `metadata`: JSON (any additional data to store)

**Outputs:**
- `rhino_guid`: String (Rhino GUID)
- `baked_successfully`: Boolean
- `layer_path`: String
- `geometry_summary`: JSON

**GH Implementation Notes:**
```
Input: Geometry ID + output parameters
Process:
  1. Retrieve geometry from parametric state
  2. Bake to specified layer
  3. Attach metadata as user text
  4. Return Rhino GUID
Output: GUID + success confirmation JSON
```

---

#### Tool 23: `explain_decision_tool_04`
**Purpose:** Generate natural language explanation of design decisions

**This is a PYTHON-SIDE tool, not a Grasshopper tool**

**Inputs:**
- `operation_history`: Array of {tool_name, parameters, timestamp}
- `evaluation_results`: JSON (from evaluation tools)
- `site_conditions`: JSON (from input tools)

**Outputs:**
- `explanation_text`: String (natural language)
- `decision_tree`: JSON (structured reasoning)
- `key_decisions`: Array of {decision, rationale}

**Implementation Notes:**
```python
# This is handled by the LLM in the reason node
# After completing operations, LLM synthesizes explanation:

# Example output:
# "Building rotated 18° to frame north view and 
# carved courtyard for daylight. L-shape responds 
# to site boundary while maintaining 30m distance 
# to road entrance. Total GFA: 8,450 m²."
```

---

## 🔄 Workflow Implementation

### Phase 1: Site Analysis
```
User: "Analyze this site"
↓
Tool 1: site_boundary_reader_04
Tool 2: context_reader_04
Tool 4: legal_constraints_reader_04
↓
Return: Site analysis summary
```

### Phase 2: Shape Generation
```
User: "Create an L-shaped building"
↓
Tool 3: shape_library_loader_04 (shape_type="l_shape")
Tool 5: parametric_shape_generator_04 (creates live geometry)
↓
Return: Initial building geometry + ID
```

### Phase 3: Constraint Validation
```
LLM automatically calls:
Tool 6: site_fit_checker_04
Tool 7: setback_checker_04
Tool 8: area_requirement_checker_04
Tool 9: adjacency_access_checker_04
Tool 10: tree_constraint_checker_04
↓
Return: Validation report + violations
```

### Phase 4: Manipulation (Iterative)
```
User: "Rotate to face the view"
↓
LLM reasons with Tool 18 (why_operation_selector_04)
↓
LLM calls: Tool 15: rotate_mirror_tool_04
↓
Return: Modified geometry

User: "Add a courtyard for light"
↓
LLM reasons with Tool 18
↓
LLM calls: Tool 14: courtyard_modifier_tool_04
↓
Return: Modified geometry with void
```

### Phase 5: Evaluation
```
LLM automatically calls:
Tool 19: spatial_intention_evaluator_04
Tool 20: performance_evaluator_04
Tool 21: shape_integrity_evaluator_04
↓
Return: Comprehensive evaluation scores
```

### Phase 6: Finalization
```
LLM calls:
Tool 22: bake_geometry_id_04 (store in Rhino)
Tool 23: explain_decision_tool_04 (generate narrative)
↓
Return: "Building rotated 18° to frame north view and 
carved courtyard for daylight. Final design achieves 
85% performance score with full code compliance."
```

---

## 📁 File Structure

```
team_04/
├── TERRAPILOT_PLAN.md                    (this file)
├── ARCHITECTURE.md                       (system architecture)
├── gh/
│   ├── team_04_definition_cluster.ghcluster    (INPUT + SHAPE tools)
│   ├── team_04_result_cluster.ghcluster        (CONSTRAINT + MANIPULATION + EVALUATION + OUTPUT tools)
│   ├── team_04_working.gh                      (test harness)
│   └── tool_definitions/                       (NEW: detailed tool definitions)
│       ├── 01_site_boundary_reader.md
│       ├── 02_context_reader.md
│       ├── ... (23 total)
│       └── 23_explain_decision.md
├── python/
│   ├── main.py                                 (entry point)
│   ├── graph.py                                (LangGraph workflow)
│   ├── _runtime/
│   │   ├── bootstrap.py
│   │   ├── config.py
│   │   ├── llm.py
│   │   └── mcp_client.py
│   └── nodes/
│       ├── reason.py                           (UPDATED: TerraPilot-specific prompts)
│       └── tools.py
└── test_cases/
    ├── test_site_01_simple_rectangle.json
    ├── test_site_02_pentagon.json
    ├── test_site_03_irregular_with_trees.json
    └── expected_outputs/
```

---

## 🎯 Implementation Priority

### Week 1: Foundation (Tools 1-5)
**Goal:** Read site data and generate basic shapes
- [ ] Tool 1: site_boundary_reader_04
- [ ] Tool 2: context_reader_04 (basic version)
- [ ] Tool 3: shape_library_loader_04 (2-3 shapes)
- [ ] Tool 4: legal_constraints_reader_04
- [ ] Tool 5: parametric_shape_generator_04

**Deliverable:** Can read a site and place a basic shape

### Week 2: Validation (Tools 6-10)
**Goal:** Validate designs against constraints
- [ ] Tool 6: site_fit_checker_04
- [ ] Tool 7: setback_checker_04
- [ ] Tool 8: area_requirement_checker_04
- [ ] Tool 9: adjacency_access_checker_04
- [ ] Tool 10: tree_constraint_checker_04

**Deliverable:** Can validate if a design is legal/feasible

### Week 3: Manipulation (Tools 11-17)
**Goal:** Modify and optimize shapes
- [ ] Tool 11: scale_shape_tool_04
- [ ] Tool 12: stretch_arm_tool_04
- [ ] Tool 13: width_modifier_tool_04
- [ ] Tool 14: courtyard_modifier_tool_04
- [ ] Tool 15: rotate_mirror_tool_04
- [ ] Tool 16: bend_angle_tool_04
- [ ] Tool 17: terrace_step_tool_04

**Deliverable:** Can manipulate shapes in response to constraints

### Week 4: Intelligence (Tools 18-23)
**Goal:** Add reasoning and evaluation
- [ ] Tool 18: why_operation_selector_04 (Python LLM logic)
- [ ] Tool 19: spatial_intention_evaluator_04
- [ ] Tool 20: performance_evaluator_04
- [ ] Tool 21: shape_integrity_evaluator_04
- [ ] Tool 22: bake_geometry_id_04
- [ ] Tool 23: explain_decision_tool_04 (Python LLM logic)

**Deliverable:** Full TerraPilot system with reasoning

---

## 🧪 Testing Strategy

### Unit Tests (Per Tool)
Each tool should have:
- Test JSON input file
- Expected output specification
- Edge case scenarios

### Integration Tests
1. **Full workflow test:** Site → Shape → Validate → Manipulate → Evaluate → Output
2. **Constraint conflict test:** What happens when no solution exists?
3. **Multi-iteration test:** Multiple manipulation steps in sequence

### Example Test Scenarios
1. **Simple L-shape on rectangular site**
   - Input: 50m x 80m rectangle, L-shape building
   - Expected: Rotated to align with street, setbacks respected

2. **Courtyard building with tree constraints**
   - Input: Pentagon site with 80 trees, U-shape building
   - Expected: Trees avoided, courtyard carved for light

3. **Sloped site with terracing**
   - Input: Trapezoidal site with 15° slope
   - Expected: Terraced building adapting to terrain

---

## 📝 System Prompt Updates

Update `nodes/reason.py` with TerraPilot-specific instructions:

```python
SYSTEM_PROMPT = """You are TerraPilot, an AI architectural assistant that designs buildings 
where 'the site argues back' and the building responds with intentional decisions.

Your goal is to help users create buildings that consciously:
- ALIGN with site features (streets, views, sun angles)
- IGNORE unimportant factors
- RESIST negative conditions (noise, poor views)
- FRAME positive spaces (plazas, courtyards)
- AVOID constraints (trees, setbacks, hazards)

You have access to 23 specialized tools organized in categories:
- INPUT TOOLS: Understand the site
- SHAPE TOOLS: Generate building forms
- CONSTRAINT TOOLS: Validate legal/physical requirements
- MANIPULATION TOOLS: Modify geometry to respond to conditions
- REASONING TOOLS: Select operations based on design intent
- EVALUATION TOOLS: Assess design quality
- OUTPUT TOOLS: Save and explain results

When the user provides a design goal, you should:
1. First understand the site (use INPUT TOOLS)
2. Generate an appropriate initial shape (use SHAPE TOOLS)
3. Validate against constraints (use CONSTRAINT TOOLS)
4. If violations exist, use MANIPULATION TOOLS to improve the design
5. Evaluate the result (use EVALUATION TOOLS)
6. Save and explain your decisions (use OUTPUT TOOLS)

Available tools:
{tool_catalog}

Always explain your reasoning in terms of what the building is responding to:
- "Rotated 18° to ALIGN with the north view"
- "Courtyard carved to FRAME the plaza"
- "Set back from road to AVOID noise"

Return JSON only:
{{"action": "final"|"tool", "final_response": "...", "tool_calls": [...]}}
"""
```

---

## 🎨 Visualization & Documentation

### For Each Operation
- Before/After geometry comparison
- Diagram showing what the building "responds to"
- Metrics comparison table

### Final Output Should Include
1. **3D Rhino model** (baked geometry)
2. **Exploded view** showing design decisions
3. **Performance dashboard** (metrics from evaluation tools)
4. **Narrative explanation** (from Tool 23)
5. **Decision tree diagram** (what influenced each choice)

---

## 🚀 Getting Started

### Step 1: Create Placeholder Tools
Create dry (but runnable) Grasshopper tools that:
- Accept JSON input
- Return mock JSON output
- Print confirmation messages

### Step 2: Test MCP Connection
Verify Python agent can discover and call placeholder tools

### Step 3: Implement One Complete Workflow
Pick the simplest path:
1. Tool 1 (read site)
2. Tool 3 (load simple bar shape)
3. Tool 6 (check if it fits)
4. Tool 22 (bake result)

### Step 4: Iterate
Add complexity one tool at a time, testing after each addition

---

## 📚 Key Decisions & Rationale

### Why 23 Tools?
Each tool has a single, clear purpose. This modularity allows:
- Easy testing in isolation
- Flexible combinations
- Clear responsibility boundaries

### Why Separate Input/Output Clusters?
Following repo structure:
- `definition_cluster`: Tools that READ or INITIALIZE (INPUT + SHAPE)
- `result_cluster`: Tools that MODIFY, EVALUATE, or OUTPUT

### Why Python-Side Reasoning?
Tools 18 and 23 are LLM-driven logic, not geometric operations. They belong in the Python agent, not Grasshopper.

### Why JSON Throughout?
- Easy to parse in both Python and Grasshopper
- Human-readable for debugging
- Standardized structure

---

## ✅ Success Criteria

### Minimum Viable Product (MVP)
- [ ] Can read a site boundary and place a building
- [ ] Can validate basic constraints (fits, setbacks)
- [ ] Can perform one manipulation (rotate or scale)
- [ ] Returns a natural language explanation

### Full System
- [ ] All 23 tools implemented and tested
- [ ] Can handle complex multi-step workflows
- [ ] Produces high-quality architectural solutions
- [ ] Generates comprehensive design narratives
- [ ] Visualization shows clear design reasoning

### Stretch Goals
- [ ] Multi-objective optimization (Pareto front)
- [ ] Real-time 3D preview in web interface
- [ ] Integration with Spacemaker or similar tools
- [ ] Machine learning from successful designs

---

## 🤝 Team Coordination

### Critical Interfaces
- **All teams:** Site boundary format (must be consistent)
- **Team X:** If they handle materials/facades, we provide geometry
- **Team Y:** If they handle MEP, we provide floor plates

### Shared Data Formats
Propose to all teams:
```json
{
  "site_boundary": {
    "type": "Polygon",
    "coordinates": [[x, y], ...]
  },
  "building_footprint": {
    "type": "Polygon", 
    "coordinates": [[x, y], ...]
  }
}
```

---

**Last Updated:** May 3, 2026  
**Team:** Team 04  
**Contact:** [Your team contact info]
