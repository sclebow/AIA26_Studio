/**
 * AgentDashboard — one screen showing WHAT the agent has and HOW it reasoned.
 *
 * Three panes, all fed by the real backend:
 *   - left   : decision graph (React Flow) — intent → brief → action → branch →
 *              select → state  (GET /sessions/{id}/decisions)
 *   - centre : 2D site plan — site, buildable zone, placed buildings, and the
 *              Pareto view-placement ghosts for the focused building
 *              (GET /sessions/{id}/explorer + /buildings/{id}/options)
 *   - right  : explorer tree — site, buildings, wings, view scores, options
 *
 * This is an example composition the app can use directly or copy from. It
 * polls nothing; call `refresh()` after a chat turn completes, or wire the SSE
 * `decision` stream (see ../README.md) for live updates.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, MiniMap } from 'reactflow';
import 'reactflow/dist/style.css';

import { nodeTypes } from '../decision-graph/nodeTypes';
import { layoutLayered, toReactFlow } from '../decision-graph/adapters';
import { SiteCanvas } from '../site/SiteCanvas';
import { ExplorerPanel } from '../explorer/ExplorerPanel';
import { Team04Api } from '../api/client';
import type { BuildingInfo, ExplorerTree, PlacementOption } from '../api/types';
import type { DecisionGraphResponse } from '../decision-graph/types';

export interface AgentDashboardProps {
  sessionId: string;
  /** Defaults to a relative-path client (same origin as the UI). */
  api?: Team04Api;
}

export function AgentDashboard({ sessionId, api = new Team04Api() }: AgentDashboardProps): JSX.Element {
  const [tree, setTree] = useState<ExplorerTree | null>(null);
  const [graph, setGraph] = useState<DecisionGraphResponse | null>(null);
  const [focusedBuildingId, setFocusedBuildingId] = useState<string | undefined>();
  const [ghostOptions, setGhostOptions] = useState<PlacementOption[]>([]);
  const [selectedOptionId, setSelectedOptionId] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [t, g] = await Promise.all([api.getExplorer(sessionId), api.getDecisions(sessionId)]);
      setTree(t);
      setGraph(g);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [api, sessionId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const focusBuilding = useCallback(
    async (buildingId: string) => {
      setFocusedBuildingId(buildingId);
      setSelectedOptionId(undefined);
      const found = tree?.buildings.find((b: BuildingInfo) => b.building_id === buildingId);
      // Prefer options already in the tree; fall back to the dedicated endpoint.
      if (found?.placement_options.length) {
        setGhostOptions(found.placement_options);
      } else {
        try {
          setGhostOptions(await api.getBuildingOptions(sessionId, buildingId));
        } catch {
          setGhostOptions([]);
        }
      }
    },
    [api, sessionId, tree],
  );

  const { rfNodes, rfEdges } = useMemo(() => {
    if (!graph) return { rfNodes: [], rfEdges: [] };
    const rf = toReactFlow(graph);
    return { rfNodes: layoutLayered(rf.nodes, rf.edges), rfEdges: rf.edges };
  }, [graph]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', fontFamily: 'system-ui, sans-serif' }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px', borderBottom: '1px solid #e2e6ea' }}>
        <strong style={{ fontSize: 14 }}>Agent Overview</strong>
        <span style={{ fontSize: 11, color: '#7f8c8d' }}>session {sessionId.slice(0, 8)}</span>
        <button onClick={() => void refresh()} style={{ marginLeft: 'auto', fontSize: 12, cursor: 'pointer' }}>
          ↻ Refresh
        </button>
      </header>

      {error && (
        <div style={{ padding: '6px 12px', background: '#fdecea', color: '#c0392b', fontSize: 12 }}>{error}</div>
      )}

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* Decision graph — how it reasoned */}
        <div style={{ flex: '1 1 40%', borderRight: '1px solid #e2e6ea', minWidth: 0 }}>
          <ReactFlow nodes={rfNodes} edges={rfEdges} nodeTypes={nodeTypes} fitView minZoom={0.2}>
            <Background />
            <MiniMap pannable zoomable />
            <Controls />
          </ReactFlow>
        </div>

        {/* Site plan — what it has */}
        <div style={{ flex: '1 1 35%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 8, minWidth: 0 }}>
          <SiteCanvas
            site={tree?.site ?? null}
            buildings={tree?.buildings ?? []}
            ghostOptions={ghostOptions}
            selectedOptionId={selectedOptionId}
            focusedBuildingId={focusedBuildingId}
            onSelectBuilding={(id) => void focusBuilding(id)}
          />
        </div>

        {/* Explorer tree */}
        <div style={{ flex: '0 0 280px', overflowY: 'auto', padding: 10 }}>
          <ExplorerPanel
            tree={tree}
            focusedBuildingId={focusedBuildingId}
            selectedOptionId={selectedOptionId}
            onFocusBuilding={(id) => void focusBuilding(id)}
            onSelectOption={(_buildingId, option) => setSelectedOptionId(option.option_id)}
          />
        </div>
      </div>
    </div>
  );
}

export default AgentDashboard;
