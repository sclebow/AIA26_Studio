# Test Case 2: Pentagon Site with Trees (From Slides)

## Scenario
Irregular pentagon site with 80 protected trees. This matches the example shown in the presentation slides.

## Site Data

```json
{
  "site": {
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
  },
  "context": {
    "roads": [
      {
        "name": "North Road",
        "centerline": [[-150, 150], [150, 150]]
      },
      {
        "name": "South Road",
        "centerline": [[-120, -130], [120, -130]]
      }
    ],
    "neighboring_buildings": [
      {
        "name": "Building A",
        "footprint": [
          [-200, 50],
          [-150, 50],
          [-150, 100],
          [-200, 100]
        ]
      }
    ],
    "entrances": [
      [0, 145],
      [0, -112]
    ],
    "view_directions": [
      {"direction": "north", "quality": "good"},
      {"direction": "south", "quality": "poor"}
    ]
  },
  "constraints": {
    "setback_all_m": 5,
    "site_coverage_max": 0.35,
    "max_height_m": 28,
    "far_max": 2.0,
    "tree_protection_mandatory": true
  },
  "program": {
    "required_gfa_sqm": 25000,
    "preferred_shape": "courtyard",
    "floors": 5,
    "courtyard_min_m": 30
  }
}
```

## Visual Reference (from slides)

```
Site Geometry (ASCII approximation):

             V1 (0, 145.1)
              *
           /     \
        /           \
      /               \
V2 (-140.9, 75.6)      V5 (140.9, 75.6)
    *                      *
     \                    /
      \                  /
       \                /
        \              /
         \            /
V3 (-108.5, -112.4)  V4 (108.5, -112.4)
          *----------*

Calculated:
- Area: ~50,000 m²
- Perimeter: ~856 m
- Circumscribed radius: ~145 m
```

## Expected Results

### Tool 1: site_boundary_reader_04
```json
{
  "success": true,
  "data": {
    "site_area_sqm": 49856.3,
    "site_centroid": [0, 0],
    "bounding_box": {
      "min": [-140.9, -112.4],
      "max": [140.9, 145.1]
    },
    "perimeter_m": 856.4,
    "number_of_sides": 5,
    "tree_locations": ["80 random points within polygon"],
    "usable_area_sqm": 46858.2
  }
}
```

### Tool 10: tree_constraint_checker_04
With a courtyard building, expect some trees in conflict:
```json
{
  "input": {
    "building_footprint": "courtyard_60x60_with_30m_void",
    "tree_locations": ["array of 80 [x,y] points"],
    "tree_radius_m": 5
  },
  "expected_output": {
    "no_conflicts": false,
    "conflicting_trees": [12, 23, 45, 67],
    "nearest_tree_distance_m": 2.3
  }
}
```

### Tool 15: rotate_mirror_tool_04
To align with north view:
```json
{
  "input": {
    "geometry_id": "terrapilot_geom_001",
    "operation": "rotate",
    "rotation_degrees": 18
  },
  "expected_output": {
    "modified_geometry": "updated_guid",
    "new_orientation_degrees": 18,
    "optimal_sun_exposure": true
  }
}
```

### Tool 19: spatial_intention_evaluator_04
```json
{
  "input": {
    "building_footprint": "rotated_courtyard",
    "view_directions": ["north_good", "south_poor"]
  },
  "expected_output": {
    "opens_to_view": true,
    "view_score": 0.85,
    "avoids_noise": true,
    "overall_spatial_score": 0.82
  }
}
```

## User Prompts to Test

### Prompt 1: Initial Generation
```
"Create a courtyard building on this irregular pentagon site that avoids the 80 protected trees"
```

**Expected workflow:**
1. site_boundary_reader_04 (includes tree placement)
2. legal_constraints_reader_04
3. parametric_shape_generator_04 (courtyard type)
4. tree_constraint_checker_04 (check conflicts)
5. If conflicts: Iterate position or size
6. Response: "Courtyard building positioned to preserve all 80 trees"

### Prompt 2: With View Orientation
```
"Rotate the building to maximize views to the north while avoiding trees"
```

**Expected workflow:**
1. Load existing geometry
2. rotate_mirror_tool_04 (try multiple angles)
3. tree_constraint_checker_04 (validate each rotation)
4. spatial_intention_evaluator_04 (score views)
5. Select best rotation
6. Response: "Building rotated 18° to ALIGN with north view while AVOIDING all protected trees"

### Prompt 3: Full Optimization
```
"Design the best possible building for this site considering trees, views, and sun exposure"
```

**Expected workflow:**
1. site_boundary_reader_04
2. context_reader_04
3. legal_constraints_reader_04
4. parametric_shape_generator_04 (courtyard)
5. tree_constraint_checker_04
6. rotate_mirror_tool_04 (optimize orientation)
7. courtyard_modifier_tool_04 (optimize void size)
8. spatial_intention_evaluator_04
9. performance_evaluator_04
10. shape_integrity_evaluator_04
11. bake_geometry_id_04
12. Response with full explanation

**Expected final response:**
```
"Courtyard building designed for optimal site response:

ALIGNMENT:
- Rotated 18° to ALIGN with north view corridor
- East wing ALIGNS with site boundary for efficiency

FRAMING:
- 35m × 35m internal courtyard FRAMES central plaza
- U-shaped opening to south FRAMES entry sequence

AVOIDANCE:
- Position and rotation AVOID all 80 protected trees (min clearance: 6.2m)
- Closed facade to south AVOIDS noise from South Road

RESISTANCE:
- Building mass RESISTS harsh south exposure
- Courtyard void RESISTS deep floor plate darkness

Performance Metrics:
- Total GFA: 26,450 m² (exceeds 25,000 m² requirement)
- Site coverage: 33% (complies with 35% max)
- Average sun hours: 6.2 hrs/day (good)
- All setbacks: 5m+ (compliant)
- Trees preserved: 80/80 (100%)
- Spatial quality score: 0.85/1.0 (excellent)
- Shape integrity score: 0.91/1.0 (excellent)

Final design successfully ALIGNS with views, FRAMES the plaza, 
AVOIDS constraints, and RESISTS negative conditions."
```

---

## Complex Manipulation Sequence

### Scenario: Building doesn't fit initially
```
User: "Create a large courtyard building with 30,000 m² GFA"
```

Initial attempt: Too large, conflicts with trees

**Expected agent reasoning:**
1. Generate large courtyard → Conflicts with trees
2. Try scale_shape_tool_04 (reduce size) → Still conflicts
3. Try rotate_mirror_tool_04 (different angle) → Better but still 3 tree conflicts
4. Try courtyard_modifier_tool_04 (larger void to reduce footprint) → Success!
5. Try stretch_arm_tool_04 (extend one wing to recover GFA) → Final success

**Final response:**
```
"After 5 iterations, found solution:
- Courtyard building rotated 25° to minimize tree conflicts
- Courtyard enlarged to 40m × 40m to reduce footprint pressure
- North wing extended by 15m to achieve 30,000 m² GFA target
- 3 trees relocated (marked for transplanting)
- Site coverage: 34.8% (compliant)"
```

---

## Testing Checklist

### Basic Functionality
- [ ] Tool 1 handles pentagon coordinates correctly
- [ ] Tool 1 places 80 trees randomly within boundary
- [ ] Tool 1 calculates area ~50,000 sqm
- [ ] Tool 5 generates courtyard shape
- [ ] Tool 10 detects tree conflicts
- [ ] Tool 15 rotates building

### Integration
- [ ] Can generate building avoiding trees
- [ ] Can optimize orientation for views
- [ ] Can explain decisions in TerraPilot style
- [ ] Multiple tool calls in sequence work
- [ ] Geometry state persists across operations

### Edge Cases
- [ ] Rotation doesn't solve tree conflicts (need position change)
- [ ] Building too large for site (need to reduce)
- [ ] No valid solution exists (graceful failure)

---

## Performance Targets

- Site boundary with 80 trees: < 200ms
- Courtyard generation: < 100ms
- Tree conflict check: < 150ms
- Rotation optimization: < 300ms
- Full workflow (10+ tools): < 3 seconds

---

## Visualization Expectations

After running this test, should see in Rhino:
- **Layer: TerraPilot_Input::SiteBoundary** - Pentagon curve
- **Layer: TerraPilot_Input::Trees** - 80 circles (r=5m)
- **Layer: TerraPilot_Geometry::Live3D** - Courtyard building mass
- **Layer: TerraPilot_Context::Roads** - Two road centerlines
- **Layer: TerraPilot_Context::Buildings** - Neighboring building

Colors suggestion:
- Site boundary: Black
- Trees: Green
- Building: Light blue
- Courtyard void: Transparent yellow
- Roads: Gray
- Neighboring buildings: Dark gray

---

## Comparison to Spacemaker

This test case should produce results comparable to Spacemaker:
- Multiple iterations to find optimal placement
- Tree avoidance as hard constraint
- View orientation as soft optimization
- Performance metrics for validation
- Natural language explanation of decisions

**Key difference:** TerraPilot explains WHY using site response philosophy (ALIGN, RESIST, FRAME, AVOID)
