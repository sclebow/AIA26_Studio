# TerraPilot Tool Catalog

This document defines the Team 04 TerraPilot tool surface in a compact format that can be copied into Grasshopper MCP tool definitions.

## Conventions

- All Grasshopper-exposed tools follow the `{tool_name}_04` naming convention.
- At the MCP boundary, the tool input is a JSON object serialized as a string.
- `Required` indicates whether the parameter should be marked as mandatory in the Grasshopper `Define Tool Parameter` component.
- Tools 18 and 23 are Python or LLM-side tools and are included here as internal interface specs.

---

## 1. site_boundary_reader_04

**Name**: `site_boundary_reader_04`

**Description**: Reads site boundary coordinates, creates the site polygon, and returns core site metrics such as area, centroid, perimeter, and optional tree-protection geometry.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `polygon_coordinates` | `array of [x, y]` | Ordered site boundary vertices in meters. First and last point do not need to repeat; the tool can close the polyline. | Yes |
| `site_area_sqm` | `number` | Optional reference area used to validate imported geometry against expected site size. | No |
| `number_of_trees` | `integer` | Number of protected trees to place or read from input assumptions. | No |
| `tree_radius_m` | `number` | Protection radius per tree in meters. | No |
| `source_label` | `string` | Optional identifier for the imported site, file, or scenario. | No |

## 2. context_reader_04

**Name**: `context_reader_04`

**Description**: Reads surrounding roads, neighboring buildings, entrances, and optional context layers, then returns organized geometry and proximity-ready metadata.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `site_boundary` | `array of [x, y]` | Site polygon used as the reference frame for context filtering and distance analysis. | Yes |
| `roads` | `array of polyline coordinate arrays` | Road centerlines or edges around the site. Each road is an array of `[x, y]` points. | No |
| `buildings` | `array of polygon coordinate arrays` | Neighbor building footprints for adjacency and overshadowing context. | No |
| `entrances` | `array of [x, y]` | Access or entry points relevant to circulation analysis. | No |
| `layer_map` | `object` | Optional mapping of semantic layer names such as `roads`, `buildings`, `entrances`, and `green`. | No |
| `analysis_radius_m` | `number` | Distance from the site boundary used to clip or filter contextual elements. | No |

## 3. shape_library_loader_04

**Name**: `shape_library_loader_04`

**Description**: Loads a predefined building typology template such as bar, L, U, H, courtyard, or cluster and returns a base footprint with default metrics.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `shape_type` | `string` | Requested library typology. Suggested values: `bar`, `l_shape`, `u_shape`, `h_shape`, `courtyard`, `cluster`. | Yes |
| `base_length_m` | `number` | Primary length of the template geometry. | No |
| `base_width_m` | `number` | Primary width of the template geometry. | No |
| `floor_count` | `integer` | Number of floors to use when estimating gross floor area. | No |
| `floor_height_m` | `number` | Height per floor for optional extrusion. | No |
| `library_variant` | `string` | Optional subtype or preset identifier, for example `compact`, `deep_plan`, or `perimeter_block`. | No |

## 4. legal_constraints_reader_04

**Name**: `legal_constraints_reader_04`

**Description**: Reads zoning or legal development constraints and computes buildable area guidance, including setbacks, height limits, coverage, and floor area allowances.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `site_boundary` | `array of [x, y]` | Site polygon used to compute buildable envelopes. | Yes |
| `front_setback_m` | `number` | Minimum front setback in meters. | No |
| `side_setback_m` | `number` | Minimum side setback in meters. | No |
| `rear_setback_m` | `number` | Minimum rear setback in meters. | No |
| `max_height_m` | `number` | Maximum permitted building height. | No |
| `max_coverage_ratio` | `number` | Maximum lot coverage, expressed as a fraction from `0` to `1`. | No |
| `max_far` | `number` | Maximum floor area ratio. | No |
| `zoning_label` | `string` | Optional zoning code or legal reference name. | No |

## 5. parametric_shape_generator_04

**Name**: `parametric_shape_generator_04`

**Description**: Creates an editable parametric building footprint and optional 3D massing using typology, size, floor, rotation, and position parameters.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `shape_base` | `string` | Base typology. Suggested values: `bar`, `l_shape`, `u_shape`, `h_shape`, `courtyard`, `cluster`. | Yes |
| `arm_length_m` | `number` | Main arm or bar length in meters. | No |
| `width_m` | `number` | Typical plan depth or bar width in meters. | No |
| `courtyard_size_m` | `number` | Courtyard dimension used by `u_shape`, `h_shape`, or courtyard types. | No |
| `rotation_degrees` | `number` | Rotation angle in degrees. | No |
| `position_xy` | `array of [x, y]` | Placement point for the footprint centroid or insertion point. | No |
| `floors` | `integer` | Number of floors for GFA and extrusion. | No |
| `floor_height_m` | `number` | Height per floor in meters. | No |

## 6. site_fit_checker_04

**Name**: `site_fit_checker_04`

**Description**: Checks whether a proposed building footprint fits within the site boundary and reports overlap, containment, and boundary clearance metrics.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `site_boundary` | `array of [x, y]` | Reference site polygon. | Yes |
| `building_boundary` | `array of [x, y]` | Proposed building footprint polygon. | Yes |
| `minimum_clearance_m` | `number` | Minimum acceptable distance from the building to the site edge. | No |
| `check_mode` | `string` | Validation mode such as `containment_only`, `clearance`, or `strict`. | No |
| `geometry_id` | `string` | Optional building identifier for tracking results across iterations. | No |

## 7. setback_checker_04

**Name**: `setback_checker_04`

**Description**: Verifies that a proposed building respects required setback distances and returns per-edge compliance metrics and violation geometry.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `site_boundary` | `array of [x, y]` | Site polygon used as the basis for setback offsets. | Yes |
| `building_boundary` | `array of [x, y]` | Proposed footprint to test against setbacks. | Yes |
| `front_setback_m` | `number` | Required setback for front edges. | No |
| `side_setback_m` | `number` | Required setback for side edges. | No |
| `rear_setback_m` | `number` | Required setback for rear edges. | No |
| `edge_classification` | `array of strings` | Optional per-site-edge labels such as `front`, `side`, and `rear`. | No |

## 8. area_requirement_checker_04

**Name**: `area_requirement_checker_04`

**Description**: Compares a generated building proposal against target footprint and gross floor area requirements and reports surplus or deficit values.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `geometry_id` | `string` | Building identifier used to connect metrics to a generated geometry. | No |
| `footprint_area_sqm` | `number` | Actual building footprint area. | Yes |
| `gross_floor_area_sqm` | `number` | Actual or estimated gross floor area. | Yes |
| `target_footprint_area_sqm` | `number` | Desired footprint area target. | No |
| `target_gfa_sqm` | `number` | Desired gross floor area target. | No |
| `tolerance_percent` | `number` | Acceptable deviation threshold expressed as a percentage. | No |

## 9. adjacency_access_checker_04

**Name**: `adjacency_access_checker_04`

**Description**: Evaluates whether the proposed building has acceptable access to roads, entrances, and circulation points, and reports key access distances.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `building_boundary` | `array of [x, y]` | Building footprint or access reference geometry. | Yes |
| `roads` | `array of polyline coordinate arrays` | Nearby roads used to measure vehicular or pedestrian access. | No |
| `entrances` | `array of [x, y]` | Entrances or access nodes relevant to the building. | No |
| `max_road_distance_m` | `number` | Maximum acceptable distance from the building to a road. | No |
| `max_entrance_distance_m` | `number` | Maximum acceptable distance from the building to an entrance point. | No |
| `path_mode` | `string` | Analysis mode such as `euclidean`, `walkway`, or `site_path`. | No |

## 10. tree_constraint_checker_04

**Name**: `tree_constraint_checker_04`

**Description**: Checks whether a building footprint conflicts with protected trees or tree protection buffers and reports any intersecting tree IDs.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `building_boundary` | `array of [x, y]` | Proposed building footprint. | Yes |
| `tree_locations` | `array of [x, y]` | Coordinates of protected trees. | Yes |
| `tree_radius_m` | `number` | Protection radius applied to each tree if no per-tree radius is supplied. | No |
| `tree_ids` | `array of strings` | Optional identifiers aligned by index with `tree_locations`. | No |
| `buffer_override_m` | `number` | Optional global override for tree protection distance. | No |

## 11. scale_shape_tool_04

**Name**: `scale_shape_tool_04`

**Description**: Scales an existing building footprint uniformly or directionally to better fit area targets or boundary conditions while preserving geometry identity.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `geometry_id` | `string` | Existing geometry identifier to retrieve and modify. | Yes |
| `scale_factor` | `number` | Uniform scale multiplier. | No |
| `target_footprint_area_sqm` | `number` | Optional target area used to derive the scale factor automatically. | No |
| `anchor_mode` | `string` | Scale anchor such as `centroid`, `entry_edge`, or `fixed_corner`. | No |
| `site_boundary` | `array of [x, y]` | Optional site polygon used to reject scaled results that leave the site. | No |

## 12. stretch_arm_tool_04

**Name**: `stretch_arm_tool_04`

**Description**: Extends or shortens one arm of a non-rectangular building type to improve fit, area, or orientation without rebuilding the entire footprint.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `geometry_id` | `string` | Existing editable geometry identifier. | Yes |
| `arm_name` | `string` | Arm or wing to modify, for example `north`, `south`, `east`, `west`, `leg_a`, or `leg_b`. | Yes |
| `delta_length_m` | `number` | Positive or negative arm extension value in meters. | Yes |
| `preserve_width` | `boolean` | Whether to keep the current arm width unchanged. | No |
| `update_gfa` | `boolean` | Whether to recalculate gross floor area in the output payload. | No |

## 13. width_modifier_tool_04

**Name**: `width_modifier_tool_04`

**Description**: Changes the width of a selected building wing or segment while preserving key corners or alignment rules when possible.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `geometry_id` | `string` | Existing geometry identifier to modify. | Yes |
| `segment_name` | `string` | Wing or segment to widen or narrow. | Yes |
| `new_width_m` | `number` | Desired final width for the selected segment. | Yes |
| `preserve_outer_face` | `boolean` | Keeps the outer face fixed and modifies inward if `true`. | No |
| `corner_lock_mode` | `string` | Strategy for corner preservation such as `none`, `start`, `end`, or `both`. | No |

## 14. courtyard_modifier_tool_04

**Name**: `courtyard_modifier_tool_04`

**Description**: Creates, enlarges, reduces, or reshapes a courtyard void inside an existing footprint and returns updated area metrics.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `geometry_id` | `string` | Existing geometry identifier to update. | Yes |
| `courtyard_action` | `string` | Operation such as `create`, `expand`, `shrink`, or `remove`. | Yes |
| `courtyard_width_m` | `number` | Courtyard width or minor dimension. | No |
| `courtyard_length_m` | `number` | Courtyard length or major dimension. | No |
| `offset_from_centroid_m` | `array of [x, y]` | Optional offset from the building centroid for the courtyard center. | No |
| `minimum_ring_width_m` | `number` | Minimum structural ring width to maintain around the courtyard. | No |

## 15. rotate_mirror_tool_04

**Name**: `rotate_mirror_tool_04`

**Description**: Rotates or mirrors an existing building geometry around a chosen pivot and returns updated orientation metadata.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `geometry_id` | `string` | Existing geometry identifier to transform. | Yes |
| `operation` | `string` | Transform type. Suggested values: `rotate`, `mirror`, or `rotate_and_mirror`. | Yes |
| `rotation_degrees` | `number` | Rotation angle in degrees for rotate operations. | No |
| `mirror_axis` | `string` | Mirror axis such as `x`, `y`, `site_major_axis`, or `custom`. | No |
| `pivot_point` | `array of [x, y]` | Optional custom pivot point. Defaults to centroid if omitted. | No |

## 16. bend_angle_tool_04

**Name**: `bend_angle_tool_04`

**Description**: Bends a selected wing or linear segment around a bend point to produce angled massing while keeping the geometry valid.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `geometry_id` | `string` | Existing geometry identifier. | Yes |
| `wing_name` | `string` | Wing or branch to bend. | Yes |
| `bend_angle_degrees` | `number` | Signed bend angle in degrees. | Yes |
| `bend_point` | `array of [x, y]` | Explicit bend location. If omitted, the tool may derive it from topology. | No |
| `preserve_area` | `boolean` | Attempts to maintain footprint area while bending. | No |

## 17. terrace_step_tool_04

**Name**: `terrace_step_tool_04`

**Description**: Applies terrace or stepped transformations to a building massing, typically in response to slope, height transitions, or daylight goals.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `geometry_id` | `string` | Existing geometry identifier to modify. | Yes |
| `step_count` | `integer` | Number of terrace levels or step transitions. | Yes |
| `step_height_m` | `number` | Vertical height difference between consecutive terraces. | Yes |
| `step_depth_m` | `number` | Horizontal retreat distance for each terrace step. | No |
| `slope_direction` | `string` | Preferred stepping direction such as `north`, `south`, `east`, `west`, or `site_fall_line`. | No |
| `terrain_profile` | `array of [x, y, z]` | Optional terrain or section control points used to adapt steps to topography. | No |

## 18. why_operation_selector_04

**Name**: `why_operation_selector_04`

**Description**: Internal Python or LLM reasoning helper that maps design intent and violation context to a recommended next operation and parameter suggestion.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `design_intent` | `string` | User or planner intent, for example `maximize courtyard`, `open views`, or `fit second building`. | Yes |
| `current_shape_type` | `string` | Current typology of the active building. | No |
| `active_violations` | `array of strings` | Current detected issues such as `setback`, `site_fit`, or `tree_conflict`. | No |
| `available_operations` | `array of strings` | Operations allowed in the current reasoning step. | Yes |
| `building_metrics` | `object` | Optional metrics payload including area, clearance, and access scores. | No |

## 19. spatial_intention_evaluator_04

**Name**: `spatial_intention_evaluator_04`

**Description**: Scores how well a proposal supports spatial intentions such as framing plazas, opening views, protecting privacy, or avoiding noise.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `building_boundary` | `array of [x, y]` | Building footprint to evaluate. | Yes |
| `site_boundary` | `array of [x, y]` | Site polygon used as the evaluation frame. | Yes |
| `intent_tags` | `array of strings` | One or more design intents to score, such as `plaza`, `views`, `privacy`, or `noise_buffer`. | Yes |
| `context_features` | `object` | Context geometry or semantic references, including roads, neighboring buildings, open spaces, and focal points. | No |
| `weight_map` | `object` | Optional score weights per intent tag. | No |

## 20. performance_evaluator_04

**Name**: `performance_evaluator_04`

**Description**: Evaluates environmental and spatial performance including solar exposure, open space, access quality, slope adaptation, and area efficiency.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `building_boundary` | `array of [x, y]` | Building footprint or evaluation geometry. | Yes |
| `site_boundary` | `array of [x, y]` | Site polygon used to derive open-space and efficiency metrics. | Yes |
| `context_data` | `object` | Environmental and surrounding data such as roads, sun vectors, terrain, and neighboring massing. | No |
| `analysis_mode` | `string` | Evaluation mode such as `fast`, `detailed`, or `ladybug`. | No |
| `target_metrics` | `object` | Optional benchmark values for performance comparison. | No |

## 21. shape_integrity_evaluator_04

**Name**: `shape_integrity_evaluator_04`

**Description**: Evaluates whether a generated or modified shape remains coherent in terms of circulation, proportions, typology recognition, and constructability.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `building_boundary` | `array of [x, y]` | Footprint or outline to evaluate. | Yes |
| `shape_type` | `string` | Expected or intended typology label. | No |
| `minimum_width_m` | `number` | Minimum acceptable building width for circulation or structure. | No |
| `maximum_aspect_ratio` | `number` | Upper bound for proportion checks. | No |
| `circulation_rules` | `object` | Optional rules for corridor width, turning radius, and connectivity checks. | No |

## 22. bake_geometry_id_04

**Name**: `bake_geometry_id_04`

**Description**: Retrieves a stored geometry by ID, bakes it into Rhino on a target layer, attaches metadata as UserText, and returns the Rhino GUID.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `geometry_id` | `string` | Geometry identifier to retrieve and bake. | Yes |
| `layer_name` | `string` | Target Rhino layer for the baked geometry. | Yes |
| `object_name` | `string` | Optional Rhino object name. | No |
| `user_text` | `object` | Additional metadata to store on the baked Rhino object. | No |
| `bake_mode` | `string` | Bake strategy such as `replace_existing`, `duplicate`, or `new_only`. | No |

## 23. explain_decision_tool_04

**Name**: `explain_decision_tool_04`

**Description**: Internal Python or LLM-side summarization helper that explains the sequence of tool decisions, tradeoffs, and final recommendation in natural language.

| Parameter Name | Type | Description | Required |
| --- | --- | --- | --- |
| `operation_history` | `array of objects` | Ordered record of tool calls, inputs, and outputs used during the workflow. | Yes |
| `final_geometry_id` | `string` | Geometry chosen as the final proposal. | No |
| `design_intent` | `string` | Original user or planner intent to explain against. | No |
| `evaluation_summary` | `object` | Aggregated scores or compliance results used to justify the decision. | No |
| `audience` | `string` | Optional audience label such as `designer`, `instructor`, or `client`. | No |

---

## Suggested Grasshopper Definition Pattern

For every Grasshopper tool, define:

1. Tool `Name`
2. Tool `Description`
3. One `Define Tool Parameter` component per parameter listed above
4. Parameter `Type` values aligned with the table entries above, usually `string`, `number`, `boolean`, `integer`, `object`, or arrays encoded in JSON

If you want, this catalog can be split next into one markdown file per remaining tool in the same style as the existing `01_` and `05_` specs.