# Team 04 Frontend

React Flow UI assets for the Team 04 agent, kept **in lockstep** with the backend.

## Lockstep policy (2026-06-16)

`BACKEND_PLAN.md` originally scheduled all frontend work for Phase 9. That is **superseded**:
every backend phase that changes a UI-visible contract ships its frontend counterpart in the
**same commit**. Concretely, when a phase adds or changes a decision-graph node, a site/explorer
overlay, or an SSE event:

1. Update `decision-graph/CONTRACT.md` (the payload contract).
2. Add/extend the component(s) + `decision-graph/types.ts` + register in `decision-graph/nodeTypes.ts`.
3. Tick the phase in `../PROGRESS.md` and reflect it in `../ARCHITECTURE.md` — same commit.

This keeps the "prompt → reasoning → result" pipeline visible to the user as the agent gets smarter,
rather than deferring all of it to the end.

Everything here lives under `team_04/` only, so it never conflicts with `main` on merge.

## Overall view — `AgentDashboard`

One screen that answers *what the agent has* and *how it reasoned*, all fed by the real backend:

- **Decision graph** (left) — the full reasoning DAG: `intent → brief → action → branch → select →
  state`, each a dedicated React Flow node. Active path highlighted; head ringed gold.
- **Site plan** (centre) — a 2D SVG plan: site boundary, buildable zone (setbacks), every placed
  building coloured by footprint family (I/L/T/U/H/Y/X/O) with label + view score, and the **Pareto
  view-placement options** of the focused building as ghosts. This is where multi-building layouts,
  shape transformations, and "placed by view analysis" become visible.
- **Explorer tree** (right) — site → buildings → wings, view scores, and the Pareto placement table.

Click a building (plan or tree) to focus it and overlay its options; click an option to highlight it.

```
frontend/
├── decision-graph/
│   ├── CONTRACT.md     # payload contract (backend ↔ frontend source of truth)
│   ├── types.ts        # decision wire types (mirror agent/models.py + schemas.py)
│   ├── BriefNode.tsx   # Phase 0 comprehension node (rich card)
│   ├── BasicNodes.tsx  # intent / action / branch / select / state nodes
│   ├── nodeTypes.ts    # React Flow registry (one component per type)
│   ├── adapters.ts     # {nodes,edges,head} + SSE events → React Flow (+ layout)
│   └── index.ts
├── site/
│   ├── geometry.ts     # bbox / projector / polygon path / type colours
│   └── SiteCanvas.tsx  # 2D plan: site, buildings, Pareto ghosts
├── explorer/
│   └── ExplorerPanel.tsx
├── clarify/
│   └── ClarifyPanel.tsx   # agent's ask-back question rendered as chips
├── api/
│   ├── types.ts        # mirror backend/schemas.py (Explorer, Session, Tools…)
│   └── client.ts       # Team04Api — typed fetch client for every JSON route
├── dashboard/
│   └── AgentDashboard.tsx
└── index.ts            # top-level barrel
```

## Backend surface → UI

| Endpoint | Consumed by |
|----------|-------------|
| `GET /sessions/{id}/decisions` | decision graph (`toReactFlow` + `nodeTypes`) |
| `POST /sessions/{id}/decisions/{node}/select` | option selection |
| `GET /sessions/{id}/explorer` | `SiteCanvas` + `ExplorerPanel` |
| `GET /sessions/{id}/buildings/{b}/options` | Pareto ghosts for a focused building |
| `GET /sessions/{id}/buildings/{b}/view` | on-demand 3D view score |
| `GET /sessions/{id}/clarification` | pending ask-back question (or null) |
| `POST /sessions/{id}/clarify` | `ClarifyPanel` submits the user's answers |
| `POST /sessions/{id}/chat` (SSE) | live `decision`/`clarify`/`token`/`tool` events |
| `GET /tools`, `POST /tools/{name}` | direct tool invocation |

## Dependencies

Installed here via `package.json` (run `npm install`, then `npm run typecheck`):

- `react` 18, `react-dom` 18, `reactflow` v11, `@microsoft/fetch-event-source`
- dev: `typescript` 5, `@types/react`, `@types/react-dom`

For `@xyflow/react` (v12) only the import paths change — the API used (`Handle`, `Position`,
`NodeProps`) is identical. `node_modules/` is git-ignored, so nothing here conflicts with `main`.

## Usage — the whole overview in one component

```tsx
import { AgentDashboard, Team04Api } from './frontend';

// Point the client at the backend (defaults to same-origin relative paths).
const api = new Team04Api('http://localhost:8000');

export function App({ sessionId }: { sessionId: string }) {
  return (
    <div style={{ height: '100vh' }}>
      <AgentDashboard sessionId={sessionId} api={api} />
    </div>
  );
}
```

The dashboard fetches `/explorer` + `/decisions` on mount and on `↻ Refresh`. It runs a built-in
layered layout (`layoutLayered`) so the decision graph renders with no extra layout dependency — swap
in dagre/elkjs if you want edge-crossing minimisation.

## Usage — decision graph only, with the live SSE stream

```tsx
import ReactFlow from 'reactflow';
import 'reactflow/dist/style.css';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { nodeTypes, toReactFlow, applyDecisionEvent } from './decision-graph';
import type { DecisionGraphResponse, DecisionNodeEvent, RFNodeData } from './decision-graph';
import { useEffect, useState } from 'react';
import type { Node, Edge } from 'reactflow';

function DecisionGraphPanel({ sessionId }: { sessionId: string }) {
  const [nodes, setNodes] = useState<Node<RFNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  // 1. Initial graph
  useEffect(() => {
    fetch(`/sessions/${sessionId}/decisions`)
      .then((r) => r.json() as Promise<DecisionGraphResponse>)
      .then((g) => {
        const rf = toReactFlow(g); // run dagre/elkjs on rf.nodes for layout
        setNodes(rf.nodes);
        setEdges(rf.edges);
      });
  }, [sessionId]);

  // 2. Live stream — the `brief` event arrives right after `intent`.
  //    Chat is POST-SSE (not a GET EventSource), so use fetch-event-source.
  //    `npm i @microsoft/fetch-event-source`
  useEffect(() => {
    const ctrl = new AbortController();
    void fetchEventSource(`/sessions/${sessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: '…user prompt…' }),
      signal: ctrl.signal,
      onmessage(msg) {
        if (msg.event !== 'decision') return; // also: token | tool | state | error | done
        const ev = JSON.parse(msg.data) as DecisionNodeEvent;
        setNodes((prev) => applyDecisionEvent(prev, ev, ev.node_id));
        // re-run layout, then optionally re-fetch /decisions to hydrate payloads
      },
    });
    return () => ctrl.abort();
  }, [sessionId]);

  return <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView />;
}
```

> Layout: the backend gives React-Flow-ready edges but no coordinates. Run a layout engine
> (dagre/elkjs) over `nodes` before rendering — `adapters.ts` leaves `position` at `(0,0)` on purpose.

## Usage — the agent asks back (clarification loop)

When a prompt is too vague, the chat stream emits a `clarify` event (and node). Render `ClarifyPanel`
with that request; on submit, POST the answers then resume with a chat turn:

```tsx
import { ClarifyPanel, Team04Api } from './frontend';
import type { ClarificationRequest } from './frontend';

function Clarify({ api, sessionId, request }:
  { api: Team04Api; sessionId: string; request: ClarificationRequest }) {
  return (
    <ClarifyPanel
      request={request}
      onSubmit={async (answers) => {
        await api.submitClarification(sessionId, answers);   // POST /clarify
        // then resume: api.chat / fetchEventSource POST /chat with a "continue" message
      }}
    />
  );
}
```

Enable it per session by setting `interactive_clarification: true` in the create-session
`layout_payload`. Policy: the agent only pauses on **critical** gaps (shape / side / view side).

## Roadmap (frontend counterpart per backend phase)

| Backend phase | Frontend artifact |
|---------------|-------------------|
| 0 Reasoning core | `AgentDashboard` ✅ — `BriefNode` + full decision-graph node set + `SiteCanvas` (shapes/multi-building/view-placement) + `ExplorerPanel` + typed API client |
| 1 Sun | `SunOverlay` ✅ — sun-vector arrow + facade-exposure points + worst-side highlight, via `POST /tools/{sun_vectors,sun_exposure,worst_sun_side}` (`api.sunVectors/sunExposure/worstSunSide`); contract in `decision-graph/CONTRACT.md` §7 |
| 2 Roads | main-road tag + per-side setback overlay |
| 3 Grid | `GridOverlay` ✅ — grid lines + nodes + chosen-side highlight + aligned placement options, via `POST /tools/{site_grid,aligned_placement}` (`api.siteGrid/alignedPlacement`); contract in `decision-graph/CONTRACT.md` §8 |
| 4 Parking | parking-lot polygons + demand badge |
| 5 Circulation/fire | entry points, routed paths, fire-access pass/fail |
| 6 Courtyard | courtyard polygon + quality readout |
| 7 Per-wing 3D | per-wing height controls (explorer hierarchy) |
| 8 Integration | full pipeline animation via SSE step events |
