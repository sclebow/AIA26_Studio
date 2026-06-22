/**
 * Backend API wire types — mirror backend/schemas.py exactly.
 *
 * Source of truth:
 *   - backend/schemas.py            (Session, Explorer, ViewAnalysis, ToolCall)
 *   - backend/routers/explorer.py   (ExplorerTree assembly)
 *   - backend/routers/sessions.py   (SessionInfo, /state, /messages)
 *   - backend/routers/decisions.py  (select response)
 *
 * Decision-graph wire types live in ../decision-graph/types.ts.
 */

export type Point = [number, number] | number[]; // backend sends [x, y] (z sometimes)
export type Polygon = number[][];

// --- Sessions -------------------------------------------------------------

export interface SessionInfo {
  session_id: string;
  created_at: string;
  message_count: number;
  building_count: number;
  has_site: boolean;
}

export interface SessionCreate {
  layout_payload: Record<string, unknown>;
  max_optimization_cycles?: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | string;
  content: string;
  message_id: string;
  timestamp: string;
  tags: string[];
}

// --- Explorer tree --------------------------------------------------------

/** One rectangular parking lot allocated on the site (Phase 4). */
export interface ParkingZone {
  zone_id: string;
  boundary: Polygon;
  stalls_allocated: number;
  area_sqm: number;
  side_index: number;
  is_main_road_side: boolean;
}

export interface SiteInfo {
  boundary: Polygon;
  area_sqm: number;
  buildable_boundary: Polygon | null;
  buildable_area_sqm: number | null;
  edge_count: number;
  site_context: Record<string, unknown>;
  /** Phase 4 — parking zones allocated on the site. */
  parking_zones: ParkingZone[];
}

export interface WingInfo {
  wing_index: number;
  role: string;
  area_sqm: number;
  centroid: number[];
}

/** One Pareto placement candidate from the view optimizer. */
export interface PlacementOption {
  option_id: string;
  rank: number;
  combined_score: number;
  unblocked_view_score: number;
  attractor_view_score: number;
  rotation_degrees: number;
  centroid_xy: number[];
  boundary: Polygon;
  outside_area_sqm: number;
  fits_within_site: boolean;
}

/** Footprint family the local generator understands (building_type may be null). */
export type BuildingType = 'I' | 'L' | 'T' | 'U' | 'H' | 'Y' | 'X' | 'O' | string;

export interface BuildingInfo {
  building_id: string;
  label: string;
  building_type: BuildingType | null;
  area_sqm: number;
  boundary: Polygon;
  centroid: number[];
  height_m: number | null;
  wings: WingInfo[];
  placement_options: PlacementOption[];
  view_score: number | null;
}

export interface ExplorerTree {
  session_id: string;
  site: SiteInfo | null;
  buildings: BuildingInfo[];
}

// --- Interactive clarification -------------------------------------------
// Mirror agent/clarify.py + backend/schemas.py (ClarificationField/Request).

export interface ClarificationField {
  key: string;        // shape | side | view_side | size | use | count
  question: string;
  options: string[];  // suggested chips
  multi: boolean;     // multi-select vs single
  allow_custom: boolean;
  critical: boolean;  // a placement-critical gap (vs nice-to-have)
}

export interface ClarificationRequest {
  summary: string;
  fields: ClarificationField[];
}

/** field key -> chosen value(s). e.g. { shape: "L", view_side: ["south"] } */
export type ClarificationAnswers = Record<string, string | string[]>;

// --- View analysis --------------------------------------------------------

export interface ViewAnalysisResult {
  view_score_3d: number;
  total_unblocked_rays: number;
  total_rays: number;
  n_floors: number;
  per_floor: Array<Record<string, unknown>>;
}

// --- Sun analysis (Phase 1) ----------------------------------------------
// Mirror agent/tools/sun_analysis.py. Returned via POST /tools/{sun_*}.

export interface SunVector {
  azimuth: number;   // compass bearing, degrees clockwise from North
  altitude: number;  // degrees above the horizon
  weight: number;
  hour?: number;     // present only in multi-hour mode
}

export interface SunFacadePoint {
  point: number[];
  outward_normal: number[];
  segment_index: number;
  exposure: number;
  normalized_exposure: number; // 0 (shaded) → 1 (fully hit)
  vectors?: Array<Record<string, unknown>>;
}

export interface SunExposureResult {
  sun_exposure_score: number;  // 0–1, LOWER is better (avoid the worst sun)
  max_possible_per_point: number;
  test_point_count: number;
  sun_vectors: SunVector[];
  worst_point: { point: number[]; normalized_exposure: number } | null;
  per_test_point: SunFacadePoint[];
}

export interface SunSide {
  edge_index: number;
  label: string;
  cardinal_hint: string;
  outward_normal: number[];
  midpoint: number[];
  length_m: number;
  sun_exposure_score: number;
  compass_sector: string;
}

export interface WorstSunSide {
  available: boolean;
  worst_side?: SunSide;
  best_side?: SunSide;
  worst_compass_sector?: string;
  per_side?: SunSide[];
  sun_vectors?: SunVector[];
  reason?: string;
}

// --- Site grid & side alignment (Phase 3) --------------------------------
// Mirror agent/tools/site_grid.py + view_optimizer.optimize_aligned_placement.

export interface SiteGrid {
  available: boolean;
  origin?: number[];
  u_axis?: number[];          // along the chosen side
  v_axis?: number[];          // perpendicular, inward
  angle_deg?: number;
  spacing?: number;
  alignment_side_index?: number;
  alignment_side_label?: string;
  grid_nodes?: number[][];          // lattice seed points
  grid_lines?: number[][][];        // [[x,y],[x,y]] segments for drawing
  adjacent_sides?: number[];
  node_count?: number;
  reason?: string;
}

/** One grid-aligned placement option from optimize_aligned_placement. */
export interface AlignedOption {
  option_id: string;
  rank: number;
  combined_score: number;
  unblocked_view_score: number;
  sun_exposure_score: number | null;
  boundary_proximity_score: number | null;
  alignment_score: number;          // ~1.0 = parallel to the chosen side
  orientation_deg: number;
  centroid_xy: number[];
  node_xy: number[] | null;
  boundary: Polygon;
  fits_within_site: boolean;
  use?: string;
  building_index?: number;
}

export interface AlignedPlacementResult {
  optimized: boolean;
  use?: string;
  objective_configs?: Array<{ name: string; weight: number }>;
  candidate_count?: number;
  feasible_count?: number;
  alignment_side_index?: number;
  orientations?: number[];
  option_count?: number;
  options: AlignedOption[];
  reason?: string;
}

// --- Road context (Phase 2) ----------------------------------------------
// Mirror agent/tools/road_context.py. Returned via POST /tools/road_context.

/** A validated road object (one entry in the site_objects list). */
export interface RoadData {
  type: 'road';
  centerline: number[][];         // [[x, y], ...]
  width_m: number;
  hierarchy: 'main' | 'secondary' | 'path';
  name?: string | null;
}

/** Per-road analysis result (from analyze_roads). */
export interface RoadAnalysis extends RoadData {
  nearest_side_index: number | null;
  distance_m: number;             // distance from centreline to nearest site side
  frontage_m: number;             // projected overlap with the nearest site side
}

/** Result of analyze_roads (POST /tools/road_context). */
export interface RoadContextResult {
  available: boolean;
  roads: RoadAnalysis[];
  main_road: RoadAnalysis | null;       // highest hierarchy → widest → most frontage
  main_road_side_index: number | null;  // site side the main road fronts
  edge_road_widths: Record<number, number>;  // {side_index: width_m} for setbacks
  updated_sides: Array<{                // site sides with adjacent_road filled in
    edge_index: number;
    label: string;
    adjacent_road: {
      name?: string | null;
      hierarchy: 'main' | 'secondary' | 'path';
      width_m: number;
      distance_m: number;
      frontage_m: number;
    } | null;
    [key: string]: unknown;
  }>;
  ambiguity: 'no_road_data' | 'no_valid_roads' | 'no_site_boundary' | null;
  ambiguity_message: string | null;
}

// --- Urban analysis (Phase 2b) -------------------------------------------
// Mirror agent/tools/urban_analysis.py + osm_context.py.
// POST /tools/urban_analysis → UrbanAnalysisResult

/** One intersection detected near (or on) the site. */
export interface IntersectionInfo {
  point: [number, number];
  type: 'crossroads' | 't_junction' | 'y_junction' | 'bend' | 'complex_junction' | 'dead_end';
  degree: number;
  distance_to_site_m: number;
}

/** One site side that adjoins a road — the site's "face" to the city. */
export interface FrontageInfo {
  side_index: number;
  road_name: string | null;
  road_hierarchy: 'main' | 'secondary' | 'path';
  road_width_m: number;
  frontage_length_m: number;
  distance_m: number;
  frontage_m: number;
  visibility_score: number;   // 0..1, higher = more publicly visible
  recommended_access: 'pedestrian' | 'primary_vehicle' | 'secondary_vehicle' | 'service';
}

/** One site corner at the junction of two frontage sides. */
export interface CornerCondition {
  corner_index: number;
  point: [number, number];
  sides: [number, number];
  road_hierarchies: [string, string];
  visibility_score: number;
  is_gateway: boolean;          // true when a main road is involved
  recommended_treatment: string;
}

/** Recommended access point on one site side. */
export interface AccessPoint {
  point: number[];
  side_index: number;
  road: string | null;
  hierarchy: string;
  road_width_m: number;
  notes: string;
}

/** Vehicle / pedestrian / service access split. */
export interface AccessRecommendation {
  vehicle: AccessPoint[];
  pedestrian: AccessPoint[];
  service: AccessPoint[];
  vehicle_count: number;
  pedestrian_count: number;
  service_count: number;
}

/** Architectural response keyed to the site type. */
export interface UrbanResponse {
  site_type: string;
  site_type_label: string;
  building_response: string;
  massing_strategy: string;
  entry_strategy: string;
  facade_strategy: string;
  corner_treatment: string | null;
  priority_frontage_side: number | null;
  secondary_frontage_side: number | null;
  gateway_corners: CornerCondition[];
  nearby_junction_type: string | null;
}

/** Full result of POST /tools/urban_analysis. */
export interface UrbanAnalysisResult {
  available: boolean;
  source: 'osm' | 'synthetic' | 'none' | string;
  site_type: string;
  frontage_count: number;
  frontages: FrontageInfo[];
  nearby_intersections: IntersectionInfo[];
  corner_conditions: CornerCondition[];
  access: AccessRecommendation;
  urban_response: UrbanResponse;
  ambiguity: string | null;
  ambiguity_message: string | null;
}

/** Interesting OSM site preset (from INTERESTING_SITES). */
export interface InterestingSite {
  name: string;
  lat: number;
  lon: number;
  radius_m: number;
  site_type_hint: string;
  description: string;
}

// --- Direct tool invocation ----------------------------------------------

export interface ToolCallResponse<R = unknown> {
  tool_name: string;
  success: boolean;
  result: R | null;
  error: string | null;
}

// --- Decision select response --------------------------------------------

export interface SelectResponse {
  selected_node_id: string;
  select_node: import('../decision-graph/types').DecisionNode;
  graph_head: string | null;
}
