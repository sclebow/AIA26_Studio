/** Decision-graph frontend module — public barrel. */
export { BriefNode, default as BriefNodeDefault } from './BriefNode';
export { nodeTypes } from './nodeTypes';
export {
  toReactFlow,
  toRFNode,
  activePathIds,
  applyDecisionEvent,
  layoutLayered,
} from './adapters';
export {
  IntentNode,
  ClarifyNode,
  ActionNode,
  BranchNode,
  SelectNode,
  StateNode,
} from './BasicNodes';
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
} from './types';
export { isBriefPayload } from './types';
