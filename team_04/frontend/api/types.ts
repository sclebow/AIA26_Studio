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

export interface SiteInfo {
  boundary: Polygon;
  area_sqm: number;
  buildable_boundary: Polygon | null;
  buildable_area_sqm: number | null;
  edge_count: number;
  site_context: Record<string, unknown>;
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
