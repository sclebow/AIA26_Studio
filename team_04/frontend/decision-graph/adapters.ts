/**
 * Adapters — convert backend decision-graph payloads into React Flow inputs.
 *
 * The backend already returns React-Flow-ready edges; nodes just need their
 * `data` packed and (optionally) a layout pass (use dagre/elkjs in the app —
 * not bundled here to stay layout-engine agnostic).
 */
import type { Edge, Node } from 'reactflow';

import type {
  DecisionGraphResponse,
  DecisionNode,
  DecisionNodeEvent,
  RFNodeData,
} from './types';

/** Pack one backend node into a React Flow node (position left at 0,0 for the layout pass). */
export function toRFNode(node: DecisionNode, head: string | null): Node<RFNodeData> {
  return {
    id: node.node_id,
    type: node.type, // resolved against nodeTypes registry; unknown → default node
    position: { x: 0, y: 0 },
    data: {
      label: node.label,
      payload: node.payload ?? {},
      isSelected: node.is_selected,
      isHead: node.node_id === head,
      nodeType: node.type,
    },
  };
}

/** Convert a full GET /decisions response into {nodes, edges} for React Flow. */
export function toReactFlow(graph: DecisionGraphResponse): {
  nodes: Node<RFNodeData>[];
  edges: Edge[];
} {
  const head = graph.head;
  const activePath = activePathIds(graph);
  const nodes = graph.nodes.map((n) => toRFNode(n, head));
  const edges: Edge[] = graph.edges.map((e) => {
    const onActive = activePath.has(e.source) && activePath.has(e.target);
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      animated: onActive,
      style: { stroke: onActive ? '#1a252f' : '#bdc3c7', strokeWidth: onActive ? 2.5 : 1 },
    };
  });
  return { nodes, edges };
}

/**
 * Minimal dependency-free layered layout: depth (root→leaf) maps to rows, order
 * within a depth maps to columns. Good enough for the decision DAG; swap in
 * dagre/elkjs in the host app if you want edge-crossing minimisation.
 * Returns a NEW node array with `position` set.
 */
export function layoutLayered(
  nodes: Node<RFNodeData>[],
  edges: Edge[],
  opts: { rowGap?: number; colGap?: number } = {},
): Node<RFNodeData>[] {
  const rowGap = opts.rowGap ?? 130;
  const colGap = opts.colGap ?? 250;

  const childrenOf = new Map<string, string[]>();
  const indeg = new Map<string, number>();
  nodes.forEach((n) => indeg.set(n.id, 0));
  edges.forEach((e) => {
    childrenOf.set(e.source, [...(childrenOf.get(e.source) ?? []), e.target]);
    indeg.set(e.target, (indeg.get(e.target) ?? 0) + 1);
  });

  const depth = new Map<string, number>();
  const roots = nodes.filter((n) => (indeg.get(n.id) ?? 0) === 0).map((n) => n.id);
  const queue: string[] = [...roots];
  roots.forEach((r) => depth.set(r, 0));
  while (queue.length) {
    const id = queue.shift() as string;
    const d = depth.get(id) ?? 0;
    for (const c of childrenOf.get(id) ?? []) {
      if (!depth.has(c) || (depth.get(c) as number) < d + 1) {
        depth.set(c, d + 1);
        queue.push(c);
      }
    }
  }

  const perRowCount = new Map<number, number>();
  return nodes.map((n) => {
    const d = depth.get(n.id) ?? 0;
    const col = perRowCount.get(d) ?? 0;
    perRowCount.set(d, col + 1);
    return { ...n, position: { x: col * colGap, y: d * rowGap } };
  });
}

/** Walk head → root via parent_id to get the active (selected) path id set. */
export function activePathIds(graph: DecisionGraphResponse): Set<string> {
  const byId = new Map(graph.nodes.map((n) => [n.node_id, n] as const));
  const ids = new Set<string>();
  let cur: string | null = graph.head;
  while (cur) {
    if (ids.has(cur)) break; // guard against cycles
    ids.add(cur);
    cur = byId.get(cur)?.parent_id ?? null;
  }
  return ids;
}

/**
 * Apply a streamed `decision` SSE event to an existing React Flow node list.
 * The compact event has no payload; if a node with this id already exists
 * (e.g. from a prior /decisions fetch) its payload is preserved.
 *
 * Returns a NEW array (immutable update) so React state setters re-render.
 */
export function applyDecisionEvent(
  current: Node<RFNodeData>[],
  ev: DecisionNodeEvent,
  head: string | null = ev.node_id,
): Node<RFNodeData>[] {
  const existing = current.find((n) => n.id === ev.node_id);
  const next: Node<RFNodeData> = {
    id: ev.node_id,
    type: ev.type,
    position: existing?.position ?? { x: 0, y: 0 },
    data: {
      label: ev.label,
      payload: existing?.data.payload ?? {},
      isSelected: ev.is_selected,
      isHead: ev.node_id === head,
      nodeType: ev.type,
    },
  };
  const others = current
    .filter((n) => n.id !== ev.node_id)
    .map((n) => (n.data.isHead ? { ...n, data: { ...n.data, isHead: n.id === head } } : n));
  return [...others, next];
}
