/**
 * Typed client for the Team 04 FastAPI backend.
 *
 * Every method maps 1:1 to a route in backend/routers/*. Chat is POST-SSE and
 * is handled separately in the UI (see ../README.md) — this client covers the
 * JSON endpoints used to render the "overall view".
 */
import type { DecisionGraphResponse } from '../decision-graph/types';
import type {
  AlignedPlacementResult,
  BuildingInfo,
  ChatMessage,
  ClarificationAnswers,
  ClarificationRequest,
  ExplorerTree,
  PlacementOption,
  RoadContextResult,
  RoadData,
  SelectResponse,
  SessionCreate,
  SessionInfo,
  SiteGrid,
  SiteInfo,
  SunExposureResult,
  SunVector,
  ToolCallResponse,
  UrbanAnalysisResult,
  ViewAnalysisResult,
  WorstSunSide,
} from './types';

export class Team04Api {
  constructor(private readonly baseUrl = '') {}

  private async get<T>(path: string): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`);
    if (!res.ok) throw new Error(`GET ${path} → ${res.status} ${res.statusText}`);
    return (await res.json()) as T;
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`POST ${path} → ${res.status} ${res.statusText}`);
    return (await res.json()) as T;
  }

  // --- Sessions -----------------------------------------------------------
  listSessions(): Promise<SessionInfo[]> {
    return this.get('/sessions');
  }
  createSession(body: SessionCreate): Promise<{ session_id: string; status: string }> {
    return this.post('/sessions', body);
  }
  getSession(id: string): Promise<SessionInfo> {
    return this.get(`/sessions/${id}`);
  }
  getState(id: string): Promise<Record<string, unknown>> {
    return this.get(`/sessions/${id}/state`);
  }
  getMessages(id: string): Promise<ChatMessage[]> {
    return this.get(`/sessions/${id}/messages`);
  }

  // --- Explorer (what the agent has) -------------------------------------
  getExplorer(id: string): Promise<ExplorerTree> {
    return this.get(`/sessions/${id}/explorer`);
  }
  getSite(id: string): Promise<SiteInfo> {
    return this.get(`/sessions/${id}/site`);
  }
  getBuildings(id: string): Promise<BuildingInfo[]> {
    return this.get(`/sessions/${id}/buildings`);
  }
  getBuilding(id: string, buildingId: string): Promise<BuildingInfo> {
    return this.get(`/sessions/${id}/buildings/${buildingId}`);
  }
  getBuildingOptions(id: string, buildingId: string): Promise<PlacementOption[]> {
    return this.get(`/sessions/${id}/buildings/${buildingId}/options`);
  }
  getBuildingView(id: string, buildingId: string): Promise<ViewAnalysisResult> {
    return this.get(`/sessions/${id}/buildings/${buildingId}/view`);
  }

  // --- Decision graph (how the agent reasons) ----------------------------
  getDecisions(id: string): Promise<DecisionGraphResponse> {
    return this.get(`/sessions/${id}/decisions`);
  }
  selectDecision(id: string, nodeId: string, reason = ''): Promise<SelectResponse> {
    return this.post(`/sessions/${id}/decisions/${nodeId}/select`, { reason });
  }

  // --- Interactive clarification (agent asks back) -----------------------
  getClarification(id: string): Promise<{ clarification_request: ClarificationRequest | null }> {
    return this.get(`/sessions/${id}/clarification`);
  }
  submitClarification(id: string, answers: ClarificationAnswers): Promise<Record<string, unknown>> {
    return this.post(`/sessions/${id}/clarify`, { answers });
  }

  // --- Tools (direct invocation) -----------------------------------------
  listTools(): Promise<{ tools: string[] }> {
    return this.get('/tools');
  }
  callTool<R = unknown>(toolName: string, args: Record<string, unknown>): Promise<ToolCallResponse<R>> {
    return this.post(`/tools/${toolName}`, { tool_name: toolName, arguments: args });
  }

  // --- Sun analysis (Phase 1) --------------------------------------------
  /** Worst-case single diagonal vector, or pass astronomy args for multi-hour. */
  sunVectors(args: Record<string, unknown> = {}): Promise<ToolCallResponse<SunVector[]>> {
    return this.callTool('sun_vectors', args);
  }
  /** Facade exposure for a building boundary against the sun vectors (lower=better). */
  sunExposure(
    buildingBoundary: number[][],
    sunVectors: SunVector[],
    obstacles: unknown[] = [],
  ): Promise<ToolCallResponse<SunExposureResult>> {
    return this.callTool('sun_exposure', {
      building_boundary: buildingBoundary,
      sun_vectors: sunVectors,
      obstacles,
    });
  }
  /** Which site side takes the worst sun, given a site_model and sun vectors. */
  worstSunSide(
    siteModel: Record<string, unknown>,
    sunVectors: SunVector[],
  ): Promise<ToolCallResponse<WorstSunSide>> {
    return this.callTool('worst_sun_side', { site_model: siteModel, sun_vectors: sunVectors });
  }

  // --- Site grid & side alignment (Phase 3) ------------------------------
  /** Derive a placement grid aligned to a chosen site side (default: longest side). */
  siteGrid(siteModel: Record<string, unknown>, args: Record<string, unknown> = {}): Promise<ToolCallResponse<SiteGrid>> {
    return this.callTool('site_grid', { site_model: siteModel, ...args });
  }
  /** Rank grid-node × aligned-orientation placements (use-driven objective mix). */
  alignedPlacement(args: Record<string, unknown>): Promise<ToolCallResponse<AlignedPlacementResult>> {
    return this.callTool('aligned_placement', args);
  }

  // --- Road context (Phase 2) --------------------------------------------
  /**
   * Analyse road objects against the site — identifies the main road, tags
   * site sides with their adjacent road, and derives edge_road_widths for the
   * setback tool.  Pass site_objects roads as `roads`.
   */
  roadContext(
    siteModel: Record<string, unknown>,
    roads: RoadData[],
  ): Promise<ToolCallResponse<RoadContextResult>> {
    return this.callTool('road_context', { site_model: siteModel, roads });
  }

  // --- Urban analysis (Phase 2b) -----------------------------------------
  /**
   * Full urban analysis: intersection classification, corner conditions,
   * access recommendations, and architectural response.
   * Pass intersections from an OSM fetch or leave empty for geometric detection.
   */
  urbanAnalysis(
    siteModel: Record<string, unknown>,
    roads: RoadData[] = [],
    intersections: Array<{ point: number[]; degree: number; type: string }> = [],
  ): Promise<ToolCallResponse<UrbanAnalysisResult>> {
    return this.callTool('urban_analysis', {
      site_model: siteModel,
      roads,
      intersections: intersections.length ? intersections : undefined,
    });
  }

  /**
   * Fetch the road network around a lat/lon from OpenStreetMap (Overpass API).
   * Returns roads + intersections ready for urbanAnalysis().
   */
  fetchUrbanSite(
    lat: number,
    lon: number,
    radiusM = 200,
  ): Promise<ToolCallResponse<{
    source: 'osm';
    lat: number; lon: number; radius_m: number;
    site_boundary: number[][];
    roads: RoadData[];
    intersections: Array<{ point: number[]; degree: number; type: string }>;
    road_count: number;
    intersection_count: number;
  }>> {
    return this.callTool('fetch_urban_site', { lat, lon, radius_m: radiusM });
  }
}

export const api = new Team04Api();
