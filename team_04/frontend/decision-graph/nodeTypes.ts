/**
 * React Flow node-type registry for the decision graph.
 *
 * Maps a backend node `type` → its component. Pass to `<ReactFlow nodeTypes={nodeTypes} />`.
 *
 * Lockstep rule (see ../README.md): every backend phase that introduces a new
 * decision-node type registers its component HERE in the same commit.
 *
 *   Phase 0 → BriefNode (`brief`)   ✅
 *   intent/action/branch/select/state → BasicNodes  ✅
 *
 * An UNKNOWN type from a newer backend falls through to React Flow's default
 * node (still renders `data.label`), so an older UI never crashes on a new node.
 */
import type { NodeTypes } from 'reactflow';

import { BriefNode } from './BriefNode';
import { IntentNode, ClarifyNode, ActionNode, BranchNode, SelectNode, StateNode } from './BasicNodes';

export const nodeTypes: NodeTypes = {
  intent: IntentNode,
  brief: BriefNode,
  clarify: ClarifyNode,
  action: ActionNode,
  branch: BranchNode,
  select: SelectNode,
  state: StateNode,
};

export default nodeTypes;
