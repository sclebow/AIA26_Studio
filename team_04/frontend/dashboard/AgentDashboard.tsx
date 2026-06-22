/**
 * AgentDashboard — three-pane view (decision graph | site plan | explorer)
 * with a chat strip wired to the real backend SSE stream.
 *
 * Back-end connections:
 *   POST /sessions/{id}/chat      → SSE stream (token / decision / clarify /
 *                                   state / error / done)
 *   GET  /sessions/{id}/explorer  → site + building tree
 *   GET  /sessions/{id}/decisions → full decision DAG
 *   GET  /sessions/{id}/buildings/{id}/options → Pareto ghost options
 *   POST /sessions/{id}/clarify   → submit clarification answers
 *
 * Live updates during streaming:
 *   - `token`    → accumulate streaming text, show cursor
 *   - `decision` → applyDecisionEvent → incremental graph update
 *   - `clarify`  → reveal ClarifyPanel above the input bar
 *   - `state`    → refresh explorer
 *   - `done`     → full refresh (explorer + decisions + layout)
 *   - `error`    → show error banner
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import ReactFlow, { Background, Controls, MiniMap } from 'reactflow';
import type { Edge, Node } from 'reactflow';
import 'reactflow/dist/style.css';

import { nodeTypes } from '../decision-graph/nodeTypes';
import { applyDecisionEvent, layoutLayered, toReactFlow } from '../decision-graph/adapters';
import type { DecisionNodeEvent, RFNodeData } from '../decision-graph/types';
import { SiteCanvas } from '../site/SiteCanvas';
import { ExplorerPanel } from '../explorer/ExplorerPanel';
import { ClarifyPanel } from '../clarify/ClarifyPanel';
import { Team04Api } from '../api/client';
import type {
  BuildingInfo,
  ClarificationAnswers,
  ClarificationRequest,
  ExplorerTree,
  PlacementOption,
} from '../api/types';

export interface AgentDashboardProps {
  sessionId: string;
  /** Defaults to a relative-path client (same origin as the UI). */
  api?: Team04Api;
}

interface ChatLine {
  role: 'user' | 'assistant';
  content: string;
}

export function AgentDashboard({
  sessionId,
  api = new Team04Api(),
}: AgentDashboardProps): JSX.Element {
  // ── Site + explorer ──────────────────────────────────────────────────────
  const [tree, setTree] = useState<ExplorerTree | null>(null);
  const [focusedBuildingId, setFocusedBuildingId] = useState<string | undefined>();
  const [ghostOptions, setGhostOptions] = useState<PlacementOption[]>([]);
  const [selectedOptionId, setSelectedOptionId] = useState<string | undefined>();

  // ── Decision graph (React Flow) ──────────────────────────────────────────
  const [rfNodes, setRfNodes] = useState<Node<RFNodeData>[]>([]);
  const [rfEdges, setRfEdges] = useState<Edge[]>([]);

  // ── Chat state ────────────────────────────────────────────────────────────
  const [messages, setMessages] = useState<ChatLine[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');

  // ── Clarification state ───────────────────────────────────────────────────
  const [clarifyRequest, setClarifyRequest] = useState<ClarificationRequest | null>(null);
  const [clarifySubmitting, setClarifySubmitting] = useState(false);

  // ── Error ──────────────────────────────────────────────────────────────────
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // ── Full refresh — replaces graph + explorer after a stream completes ──────
  const refresh = useCallback(async () => {
    try {
      const [t, g] = await Promise.all([
        api.getExplorer(sessionId),
        api.getDecisions(sessionId),
      ]);
      setTree(t);
      const rf = toReactFlow(g);
      setRfNodes(layoutLayered(rf.nodes, rf.edges));
      setRfEdges(rf.edges);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [api, sessionId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Auto-scroll messages pane
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  // ── Focus a building ───────────────────────────────────────────────────────
  const focusBuilding = useCallback(
    async (buildingId: string) => {
      setFocusedBuildingId(buildingId);
      setSelectedOptionId(undefined);
      const found = tree?.buildings.find((b: BuildingInfo) => b.building_id === buildingId);
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

  // ── Send a message — streams SSE from POST /sessions/{id}/chat ─────────────
  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || streaming) return;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setMessages((prev) => [...prev, { role: 'user', content: text }]);
      setInput('');
      setStreaming(true);
      setStreamingText('');
      setClarifyRequest(null);
      setError(null);

      let accumulated = '';

      try {
        await fetchEventSource(`${api.baseUrl}/sessions/${sessionId}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text }),
          signal: controller.signal,
          openWhenHidden: true,

          onmessage(ev) {
            if (ev.event === 'token') {
              accumulated += ev.data;
              setStreamingText(accumulated);
            } else if (ev.event === 'decision') {
              try {
                const node = JSON.parse(ev.data) as DecisionNodeEvent;
                setRfNodes((prev) => applyDecisionEvent(prev, node, node.node_id));
                if (node.parent_id) {
                  setRfEdges((prev) => {
                    const edgeId = `e-${node.parent_id}-${node.node_id}`;
                    if (prev.find((e) => e.id === edgeId)) return prev;
                    return [
                      ...prev,
                      {
                        id: edgeId,
                        source: node.parent_id as string,
                        target: node.node_id,
                        animated: true,
                        style: { stroke: '#1a252f', strokeWidth: 2.5 },
                      },
                    ];
                  });
                }
              } catch {
                // ignore parse errors
              }
            } else if (ev.event === 'clarify') {
              try {
                setClarifyRequest(JSON.parse(ev.data) as ClarificationRequest);
              } catch {
                // ignore
              }
            } else if (ev.event === 'state') {
              // Partial state — refresh explorer to show new buildings
              void refresh();
            } else if (ev.event === 'error') {
              setError(ev.data);
            } else if (ev.event === 'done') {
              if (accumulated) {
                setMessages((prev) => [...prev, { role: 'assistant', content: accumulated }]);
              }
              setStreamingText('');
              setStreaming(false);
              void refresh(); // full layout pass + explorer sync
            }
          },

          onerror(err) {
            // Throw so fetchEventSource stops retrying
            throw err;
          },
        });
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          setError(e instanceof Error ? e.message : 'Connection failed');
        }
        setStreaming(false);
        setStreamingText('');
      }
    },
    [api, sessionId, streaming, refresh],
  );

  // ── Clarification submit → POST /clarify then resume chat ─────────────────
  const submitClarification = useCallback(
    async (answers: ClarificationAnswers) => {
      setClarifySubmitting(true);
      try {
        await api.submitClarification(sessionId, answers);
        setClarifyRequest(null);
        await sendMessage('continue');
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Clarification failed');
      } finally {
        setClarifySubmitting(false);
      }
    },
    [api, sessionId, sendMessage],
  );

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        fontFamily: 'system-ui, sans-serif',
      }}
    >
      {/* Header */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '8px 12px',
          borderBottom: '1px solid #e2e6ea',
          flexShrink: 0,
        }}
      >
        <strong style={{ fontSize: 14 }}>Agent Overview</strong>
        <span style={{ fontSize: 11, color: '#7f8c8d' }}>session {sessionId.slice(0, 8)}</span>
        {streaming && (
          <span style={{ fontSize: 11, color: '#2980b9' }}>● thinking…</span>
        )}
        <button
          onClick={() => void refresh()}
          disabled={streaming}
          style={{ marginLeft: 'auto', fontSize: 12, cursor: streaming ? 'default' : 'pointer' }}
        >
          ↻ Refresh
        </button>
      </header>

      {/* Error banner */}
      {error && (
        <div
          style={{ padding: '6px 12px', background: '#fdecea', color: '#c0392b', fontSize: 12, flexShrink: 0 }}
        >
          {error}
        </div>
      )}

      {/* Three-pane area */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* Left — decision graph */}
        <div style={{ flex: '1 1 40%', borderRight: '1px solid #e2e6ea', minWidth: 0 }}>
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            nodeTypes={nodeTypes}
            fitView
            minZoom={0.2}
          >
            <Background />
            <MiniMap pannable zoomable />
            <Controls />
          </ReactFlow>
        </div>

        {/* Centre — site plan */}
        <div
          style={{
            flex: '1 1 35%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 8,
            minWidth: 0,
          }}
        >
          <SiteCanvas
            site={tree?.site ?? null}
            buildings={tree?.buildings ?? []}
            ghostOptions={ghostOptions}
            selectedOptionId={selectedOptionId}
            focusedBuildingId={focusedBuildingId}
            onSelectBuilding={(id) => void focusBuilding(id)}
          />
        </div>

        {/* Right — explorer */}
        <div style={{ flex: '0 0 280px', overflowY: 'auto', padding: 10, borderLeft: '1px solid #e2e6ea' }}>
          <ExplorerPanel
            tree={tree}
            focusedBuildingId={focusedBuildingId}
            selectedOptionId={selectedOptionId}
            onFocusBuilding={(id) => void focusBuilding(id)}
            onSelectOption={(_buildingId, option) => setSelectedOptionId(option.option_id)}
          />
        </div>
      </div>

      {/* Chat strip */}
      <div
        style={{
          borderTop: '2px solid #e2e6ea',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: 300,
          background: '#f8fafc',
          flexShrink: 0,
        }}
      >
        {/* Message log */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '8px 12px',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            minHeight: 60,
          }}
        >
          {messages.length === 0 && !streamingText && (
            <span style={{ fontSize: 11, color: '#95a5a6', alignSelf: 'center', marginTop: 8 }}>
              Describe what you want to design — the agent will place buildings on the site.
            </span>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                background: m.role === 'user' ? '#2980b9' : '#ecf0f1',
                color: m.role === 'user' ? '#fff' : '#2c3e50',
                borderRadius: 10,
                padding: '5px 10px',
                fontSize: 12,
                maxWidth: '75%',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {m.content}
            </div>
          ))}
          {streamingText && (
            <div
              style={{
                alignSelf: 'flex-start',
                background: '#ecf0f1',
                color: '#2c3e50',
                borderRadius: 10,
                padding: '5px 10px',
                fontSize: 12,
                maxWidth: '75%',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {streamingText}
              <span style={{ opacity: 0.4 }}>▍</span>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Clarify panel — shown when agent asks back */}
        {clarifyRequest && (
          <div style={{ padding: '6px 12px', borderTop: '1px solid #e2e6ea' }}>
            <ClarifyPanel
              request={clarifyRequest}
              onSubmit={(answers: ClarificationAnswers) => void submitClarification(answers)}
              submitting={clarifySubmitting}
            />
          </div>
        )}

        {/* Input bar */}
        <div
          style={{
            display: 'flex',
            gap: 8,
            padding: '8px 12px',
            borderTop: '1px solid #e2e6ea',
          }}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void sendMessage(input);
              }
            }}
            placeholder="Describe your design… (Enter to send, Shift+Enter for new line)"
            disabled={streaming}
            rows={2}
            style={{
              flex: 1,
              resize: 'none',
              borderRadius: 8,
              border: '1px solid #cdd5dd',
              padding: '6px 10px',
              fontSize: 12,
              fontFamily: 'inherit',
              background: streaming ? '#f0f4f8' : '#fff',
              outline: 'none',
            }}
          />
          <button
            type="button"
            onClick={() => void sendMessage(input)}
            disabled={streaming || !input.trim()}
            style={{
              padding: '0 18px',
              borderRadius: 8,
              border: 'none',
              background: streaming || !input.trim() ? '#bdc8d2' : '#2980b9',
              color: '#fff',
              fontSize: 12,
              fontWeight: 600,
              cursor: streaming || !input.trim() ? 'not-allowed' : 'pointer',
              alignSelf: 'stretch',
              minWidth: 64,
            }}
          >
            {streaming ? '…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default AgentDashboard;
