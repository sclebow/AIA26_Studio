/**
 * Decision-graph wire types — mirror the Team 04 backend exactly.
 *
 * Backend source of truth:
 *   - backend/schemas.py            (DecisionNodeSchema)
 *   - backend/decision_graph.py     (node constructors + to_dict)
 *   - backend/routers/chat.py       (`decision` SSE event = compact node)
 *   - agent/models.py               (DesignBrief / BuildingSpec → payload.design_brief)
 *
 * See CONTRACT.md for the full per-type payload table. Keep these types in sync
 * with that contract in the SAME commit a backend phase changes a payload.
 */

/** Footprint families the generator understands, plus "auto" = let the agent decide. */
export type ShapePreference =
  | 'I' | 'L' | 'T' | 'U' | 'H' | 'Y' | 'X' | 'O' | 'auto';

/** Known node types. Kept as a union, but the wire field is an open string —
 *  always handle the `default`/unknown case so an old UI survives a new backend. */
export type DecisionNodeType =
  | 'intent' | 'brief' | 'clarify' | 'action' | 'branch' | 'select' | 'state';

/** One building's intent inside a DesignBrief (agent/models.py BuildingSpec). */
export interface BuildingSpec {
  shape_preference: ShapePreference;
  footprint_area_sqm: number | null;
  storeys: number | null;
  use: string;
  intent_text: string;
}

/** The typed comprehension of the user's prompt (agent/models.py DesignBrief.to_state()). */
export interface DesignBrief {
  building_count: number;
  buildings: BuildingSpec[];
  courtyard_requested: boolean;
  courtyard_qualities: string[];
  parking_requested: boolean;
  requested_rotation_deg: number | null;
  view_weight: number;      // 0..1
  sun_weight: number;       // 0..1
  alignment_weight: number; // 0..1
  ambiguities: string[];
  source: 'llm' | 'fallback';
}

/** payload shape for a `brief` node. */
export interface BriefPayload {
  design_brief: DesignBrief;
}

/** Full node as returned by GET /sessions/{id}/decisions. */
export interface DecisionNode<P = Record<string, unknown>> {
  node_id: string;
  parent_id: string | null;
  type: DecisionNodeType | string; // open string on the wire
  label: string;
  timestamp: string;               // ISO-8601 UTC
  is_selected: boolean;
  payload: P;
}

/** Compact node from the `decision` SSE event (no payload/timestamp). */
export interface DecisionNodeEvent {
  node_id: string;
  type: DecisionNodeType | string;
  label: string;
  parent_id: string | null;
  is_selected: boolean;
}

/** Edge shape — already React-Flow-ready from the backend. */
export interface DecisionEdge {
  id: string;
  source: string;
  target: string;
}

/** GET /sessions/{id}/decisions response. */
export interface DecisionGraphResponse {
  nodes: DecisionNode[];
  edges: DecisionEdge[];
  head: string | null;
}

/** `data` object we attach to each React Flow node (see adapters.ts). */
export interface RFNodeData {
  label: string;
  payload: Record<string, unknown>;
  isSelected: boolean;
  isHead: boolean;
  nodeType: DecisionNodeType | string;
}

/** Narrowing helper: is this node's payload a brief payload? */
export function isBriefPayload(payload: unknown): payload is BriefPayload {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    typeof (payload as BriefPayload).design_brief === 'object' &&
    (payload as BriefPayload).design_brief !== null
  );
}
