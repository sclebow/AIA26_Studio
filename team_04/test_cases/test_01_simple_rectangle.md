# Test Case 1: Simple Rectangular Site

## Scenario
Basic rectangular site with no complications. Good for initial tool testing.

## Site Data

```json
{
  "site": {
    "polygon_coordinates": [
      [0, 0],
      [100, 0],
      [100, 80],
      [0, 80]
    ],
    "site_area_sqm": 8000,
    "number_of_trees": 0,
    "tree_radius_m": 0
  },
  "context": {
    "roads": [
      {
        "name": "Main Street",
        "centerline": [[0, -10], [100, -10]]
      }
    ],
    "entrances": [
      [50, 0]
    ]
  },
  "constraints": {
    "setback_north_m": 5,
    "setback_south_m": 3,
    "setback_east_m": 3,
    "setback_west_m": 3,
    "site_coverage_max": 0.4,
    "max_height_m": 24,
    "far_max": 1.5
  },
  "program": {
    "required_gfa_sqm": 8000,
    "required_footprint_sqm": 2000,
    "floors": 4
  }
}
```

## Expected Results

### Tool 1: site_boundary_reader_04
```json
{
  "success": true,
  "data": {
    "site_area_sqm": 8000,
    "site_centroid": [50, 40],
    "bounding_box": {
      "min": [0, 0],
      "max": [100, 80]
    },
    "perimeter_m": 360,
    "number_of_sides": 4
  }
}
```

### Tool 4: legal_constraints_reader_04
```json
{
  "success": true,
  "data": {
    "buildable_area_sqm": 7140,
    "max_footprint_sqm": 3200,
    "max_gfa_sqm": 12000
  }
}
```

### Tool 3: shape_library_loader_04 (bar shape)
```json
{
  "input": {
    "shape_type": "bar",
    "base_width_m": 15,
    "base_length_m": 60,
    "floors": 4,
    "floor_height_m": 3.5
  },
  "expected_output": {
    "footprint_area_sqm": 900,
    "gfa_sqm": 3600,
    "total_height_m": 14
  }
}
```

### Tool 6: site_fit_checker_04
```json
{
  "input": {
    "building_footprint": "bar_at_origin",
    "site_boundary": "rectangle_100x80"
  },
  "expected_output": {
    "fits": true,
    "overlap_area_sqm": 0,
    "distance_to_boundary_m": 10
  }
}
```

## User Prompts to Test

### Prompt 1: Simple Generation
```
"Create a bar building on this rectangular site"
```

**Expected workflow:**
1. site_boundary_reader_04
2. parametric_shape_generator_04 (shape="bar")
3. site_fit_checker_04
4. Response: "Bar building created: 60m x 15m, 4 floors, 3600 m² GFA"

### Prompt 2: With Validation
```
"Create a building that meets the program requirements"
```

**Expected workflow:**
1. site_boundary_reader_04
2. legal_constraints_reader_04
3. parametric_shape_generator_04
4. area_requirement_checker_04
5. If insufficient: scale_shape_tool_04
6. Response: "Building designed to achieve 8,000 m² GFA requirement"

### Prompt 3: With Orientation
```
"Create a building facing Main Street"
```

**Expected workflow:**
1. site_boundary_reader_04
2. context_reader_04
3. parametric_shape_generator_04
4. rotate_mirror_tool_04 (orient to street)
5. Response: "Building oriented parallel to Main Street on south edge"

---

## Testing Checklist

- [ ] Tool 1 returns correct area (8000 sqm)
- [ ] Tool 1 returns correct centroid [50, 40]
- [ ] Tool 3 loads bar shape successfully
- [ ] Tool 5 generates parametric bar
- [ ] Tool 6 confirms building fits
- [ ] Tool 7 confirms setbacks met
- [ ] Tool 8 confirms area requirements
- [ ] Full workflow: Site → Shape → Validation works

---

## Variations

### Variant A: Larger Building
Change required_gfa_sqm to 12000
- Should generate 6 floors OR larger footprint

### Variant B: Strict Setbacks
Change all setbacks to 10m
- Buildable area reduces to 4800 sqm
- Must adapt building size

### Variant C: Height Limit
Change max_height_m to 15
- Must limit to 4 floors max
- Must increase footprint for GFA
