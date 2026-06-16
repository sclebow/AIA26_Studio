/**
 * Typed client for the Team 04 FastAPI backend.
 *
 * Every method maps 1:1 to a route in backend/routers/*. Chat is POST-SSE and
 * is handled separately in the UI (see ../README.md) — this client covers the
 * JSON endpoints used to render the "overall view".
 */
import type { DecisionGraphResponse } from '../decision-graph/types';
import type {
  BuildingInfo,
  ChatMessage,
  ClarificationAnswers,
  ClarificationRequest,
  ExplorerTree,
  PlacementOption,
  SelectResponse,
  SessionCreate,
  SessionInfo,
  SiteInfo,
  ToolCallResponse,
  ViewAnalysisResult,
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
}

export const api = new Team04Api();
