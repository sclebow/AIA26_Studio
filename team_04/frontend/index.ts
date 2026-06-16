/** Team 04 frontend — top-level barrel. */

// Decision graph
export {
  BriefNode,
  nodeTypes,
  toReactFlow,
  toRFNode,
  activePathIds,
  applyDecisionEvent,
  layoutLayered,
} from './decision-graph';
export {
  IntentNode,
  ClarifyNode,
  ActionNode,
  BranchNode,
  SelectNode,
  StateNode,
} from './decision-graph/BasicNodes';

// Clarification (agent asks back)
export { ClarifyPanel } from './clarify/ClarifyPanel';
export type {
  ShapePreference,
  DecisionNodeType,
  BuildingSpec,
  DesignBrief,
  BriefPayload,
  DecisionNode,
  DecisionNodeEvent,
  DecisionEdge,
  DecisionGraphResponse,
  RFNodeData,
} from './decision-graph';
export { isBriefPayload } from './decision-graph';

// Site plan
export { SiteCanvas } from './site/SiteCanvas';
export {
  computeBBox,
  makeProjector,
  polygonToPath,
  centroidOf,
  buildingColor,
  BUILDING_TYPE_COLORS,
} from './site/geometry';

// Explorer
export { ExplorerPanel } from './explorer/ExplorerPanel';

// Dashboard
export { AgentDashboard } from './dashboard/AgentDashboard';

// API
export { Team04Api, api } from './api/client';
export type {
  SessionInfo,
  SessionCreate,
  ChatMessage,
  SiteInfo,
  WingInfo,
  PlacementOption,
  BuildingType,
  BuildingInfo,
  ExplorerTree,
  ViewAnalysisResult,
  ToolCallResponse,
  SelectResponse,
  ClarificationField,
  ClarificationRequest,
  ClarificationAnswers,
  Point,
  Polygon,
} from './api/types';
