import React, { useState, useEffect, useCallback, useRef } from 'react';
import ThreeViewport from './components/ThreeViewport/ThreeViewport';
import ProposalBanner from './components/ThreeViewport/ProposalBanner';
import LayerToggle from './components/LayerToggle';
import GraphPanel from './components/GraphPanel/GraphPanel';
import ChatPanel from './components/ChatPanel/ChatPanel';
import Dashboard from './components/Dashboard/Dashboard';
import ProcessPanel from './components/ProcessPanel/ProcessPanel';
import LayoutLoader from './components/LayoutLoader/LayoutLoader';
import SelectionPanel from './components/ThreeViewport/SelectionPanel';
import ReasoningLog from './components/ReasoningLog/ReasoningLog';
import ThemeToggle, { useTheme } from './components/common/ThemeToggle';
import FloatingPanel from './components/common/FloatingPanel';
import { useWebSocket } from './hooks/useWebSocket';
import { useSelectionSync } from './hooks/useSelectionSync';
import { useLayoutState } from './hooks/useLayoutState';
import { useAgentState } from './hooks/useAgentState';
import WelcomePage from "./components/WelcomePage";
import OnboardingPage, { OnboardingData } from "./components/OnboardingPage";
import type { LayerVisibility, LayerName } from './types';

const defaultVisibility: LayerVisibility = {
  outline: true, rooms: true, doors: true, windows: true,
  furniture: true, mep: true, structure: true,
};

type ViewMode = 'geometry' | 'graph';

const IconLog = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
  </svg>
);

export default function App() {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';
  const ws = useWebSocket();
  const { selectedId, select, applyRemoteSelection } = useSelectionSync(ws);
  const layoutState = useLayoutState();
  const agentState = useAgentState({ onScoresReady: layoutState.setScores });

  // Auth gates
  const [loggedIn, setLoggedIn] = useState(false);
  const [onboarded, setOnboarded] = useState(false);
  const [onboardingData, setOnboardingData] = useState<OnboardingData | null>(null);

  // UI state
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(defaultVisibility);
  const [showLabels, setShowLabels] = useState(true);   // shared: 3D labels + graph labels
  const [viewMode, setViewMode] = useState<ViewMode>('geometry');
  const [displayMode, setDisplayMode] = useState<ViewMode>('geometry');
  const [animPhase, setAnimPhase] = useState<'idle' | 'out' | 'in'>('idle');
  const [logOpen, setLogOpen] = useState(false);
  const animTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wasRunningRef = useRef(false);

  // ── WebSocket dispatcher ──────────────────────────────────────────────────
  // Subscribe to EVERY message (not ws.lastMessage, which coalesces bursts and
  // would drop e.g. an agent_response that is immediately followed by a
  // state_update). dispatchRef holds the latest handlers to avoid re-subscribing.
  const dispatchRef = useRef<(msg: typeof ws.lastMessage) => void>(() => {});
  dispatchRef.current = (msg) => {
    if (!msg) return;
    switch (msg.type) {
      case 'agent_event':      agentState.handleAgentEvent(msg);      break;
      case 'agent_response':   agentState.handleAgentResponse(msg);   break;
      case 'agent_say':        agentState.handleAgentSay(msg);        break;
      case 'agent_checkpoint': agentState.handleAgentCheckpoint(msg); break;
      case 'state_update':     layoutState.updateFromWS(msg);         break;
      case 'selection_sync':   applyRemoteSelection(msg.elementId, msg.source); break;
    }
  };
  useEffect(() => ws.subscribe((msg) => dispatchRef.current(msg)), [ws]);

  // ── Auto-load layout ──────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      await layoutState.fetchLayouts();
      if (!layoutState.layout) await layoutState.loadLayout('industrial_005');
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Poll layout from disk while agent is running ──────────────────────────
  useEffect(() => {
    if (agentState.isAgentRunning && !layoutState.isPending) {
      wasRunningRef.current = true;
      const interval = setInterval(() => { layoutState.reloadLayout(); }, 3000);
      return () => clearInterval(interval);
    } else if (wasRunningRef.current && !layoutState.isPending) {
      wasRunningRef.current = false;
      layoutState.reloadLayout();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentState.isAgentRunning, layoutState.isPending]);

  // ── View mode switch with fade/scale animation ────────────────────────────
  const switchMode = useCallback((next: ViewMode) => {
    if (next === viewMode || animPhase !== 'idle') return;
    setViewMode(next);
    setAnimPhase('out');
    if (animTimerRef.current) clearTimeout(animTimerRef.current);
    animTimerRef.current = setTimeout(() => {
      setDisplayMode(next);
      setAnimPhase('in');
      animTimerRef.current = setTimeout(() => setAnimPhase('idle'), 180);
    }, 180);
  }, [viewMode, animPhase]);

  useEffect(() => () => { if (animTimerRef.current) clearTimeout(animTimerRef.current); }, []);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleToggleLayer = useCallback((layer: LayerName) => {
    setLayerVisibility(prev => ({ ...prev, [layer]: !prev[layer] }));
  }, []);

  const handleChatSend = useCallback((content: string) => {
    agentState.addUserMessage(content);
    ws.send({ type: 'chat_message', content });
  }, [agentState, ws]);

  // A chip from the options panel (s1, yes, end, "rule: ...") — sent as a decision.
  const handleChatDecision = useCallback((value: string) => {
    agentState.beginAwaitingResponse();
    ws.send({ type: 'chat_decision', value });
  }, [agentState, ws]);

  const handleChatReset  = useCallback(() => { agentState.resetChat(); }, [agentState]);
  const handleChatCancel = useCallback(() => { agentState.cancelLast(); }, [agentState]);

  const handleLayoutSelect = useCallback(async (name: string) => {
    await layoutState.loadLayout(name);
  }, [layoutState]);

  const handleLayoutUpload = useCallback(async (file: File) => {
    await layoutState.uploadLayout(file);
  }, [layoutState]);

  const handleViewportSelect = useCallback((id: string | null) => { select(id, 'viewport'); }, [select]);
  const handleGraphSelect    = useCallback((id: string | null) => { select(id, 'graph'); }, [select]);

  const handleObserverPoint = useCallback((x: number, y: number, height: number, pointStr: string) => {
    ws.send({ type: 'observer_point', x, y, height, point_str: pointStr });
  }, [ws]);

  const handleObserverPath = useCallback((points: Array<{ x: number; y: number }>) => {
    const path_str = points.map(p => `${p.x.toFixed(3)},${p.y.toFixed(3)}`).join(';');
    ws.send({ type: 'observer_path', path_str, height: 1.7 });
  }, [ws]);

  // ── Auth gates ────────────────────────────────────────────────────────────
  if (!loggedIn) return <WelcomePage onEnter={() => setLoggedIn(true)} />;
  if (!onboarded) return <OnboardingPage onComplete={(data) => { setOnboardingData(data); setOnboarded(true); }} />;

  // ── Shared style tokens ───────────────────────────────────────────────────
  const sidebarBg = isDark ? 'rgba(13,9,24,0.98)' : 'rgba(248,249,251,0.98)';
  const panelBorder = `1px solid ${colors.border}`;

  const sectionHeaderStyle: React.CSSProperties = {
    padding: '7px 12px',
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: '0.14em',
    textTransform: 'uppercase',
    color: colors.muted,
    fontFamily: colors.fontHeading,
    borderBottom: panelBorder,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexShrink: 0,
    userSelect: 'none',
  };

  // Animation wrapper style — both CENTER and RIGHT-top share this so they animate in sync.
  const swapStyle: React.CSSProperties = {
    opacity: animPhase === 'out' ? 0 : 1,
    transform: animPhase === 'out' ? 'scale(0.96)' : 'scale(1)',
    transition: 'opacity 180ms ease, transform 180ms ease',
    width: '100%',
    height: '100%',
  };

  // ── ThreeViewport — shared props to avoid repetition ─────────────────────
  const viewportProps = layoutState.layout ? {
    layout: layoutState.layout,
    selectedId,
    onSelect: handleViewportSelect,
    layers: layerVisibility,
    graphData: layoutState.graphData,
    modifiedIds: layoutState.modifiedIds,
    onObserverPoint: handleObserverPoint,
    onObserverPath: handleObserverPath,
    showLabels,
    onToggleLabels: () => setShowLabels(v => !v),
    isAgentRunning: agentState.isAgentRunning,
  } : null;

  const noLayoutPlaceholder = (
    <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: colors.muted, fontSize: 12, flexDirection: 'column', gap: 8 }}>
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={colors.accentDim} strokeWidth="1.5">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
        <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
        <line x1="12" y1="22.08" x2="12" y2="12" />
      </svg>
      No layout loaded
    </div>
  );

  return (
    <div style={{ width: '100vw', height: '100vh', background: colors.bg, color: colors.text, fontFamily: colors.font, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>

      {/* ══════════════════════════════════════════════════════════════════════
          TOP NAV BAR
      ══════════════════════════════════════════════════════════════════════ */}
      <div style={{
        height: 44, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 16px', zIndex: 250,
        background: isDark ? 'rgba(13,9,24,0.96)' : 'rgba(245,245,247,0.97)',
        borderBottom: panelBorder,
      }}>

        {/* Logo — matches the welcome page (logo.png + SPATIAL FLOW) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <img src="/logo.png" alt="logo" style={{
            width: 30, height: 30, objectFit: 'contain',
            filter: 'hue-rotate(200deg) saturate(1.3)',
          }} />
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
            <span style={{
              fontSize: 8, letterSpacing: '0.32em', color: 'rgba(167,139,250,0.55)',
              textTransform: 'uppercase', fontFamily: colors.fontHeading,
            }}>AIA Studio 2026</span>
            <span style={{
              fontSize: 14, fontWeight: 700, letterSpacing: '0.18em', color: '#e9d5ff',
              textTransform: 'uppercase', fontFamily: colors.fontHeading,
            }}>SPATIAL FLOW</span>
          </div>
        </div>

        {/* View mode pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)', borderRadius: 10, padding: 3, border: panelBorder }}>
          {(['geometry', 'graph'] as ViewMode[]).map(m => (
            <button key={m} onClick={() => switchMode(m)} style={{
              padding: '5px 16px', borderRadius: 8, border: 'none',
              fontSize: 12, fontWeight: 500, letterSpacing: '0.02em',
              cursor: 'pointer', fontFamily: colors.font, transition: 'all 0.2s',
              background: viewMode === m ? (isDark ? 'rgba(139,92,246,0.15)' : 'rgba(124,58,237,0.12)') : 'transparent',
              color: viewMode === m ? colors.accent : colors.muted,
            }}>
              {m === 'geometry' ? '3D Viewport' : 'Spatial Graph'}
            </button>
          ))}
        </div>

        {/* Right: Log + WS dot + Theme */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button onClick={() => setLogOpen(v => !v)} style={{
            padding: '3px 8px', borderRadius: 6,
            border: `1px solid ${logOpen ? colors.accent + '30' : 'transparent'}`,
            fontSize: 10, fontWeight: 500, letterSpacing: '0.04em', textTransform: 'uppercase',
            cursor: 'pointer', fontFamily: colors.font, transition: 'all 0.2s',
            background: logOpen ? colors.accentDim : 'transparent',
            color: logOpen ? colors.accent : colors.muted,
          }}>
            Log
          </button>
          <div style={{
            width: 6, height: 6, borderRadius: '50%',
            background: ws.isConnected ? colors.success : colors.error,
            boxShadow: ws.isConnected ? `0 0 6px ${colors.success}` : `0 0 6px ${colors.error}`,
          }} />
          <ThemeToggle />
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════════════════
          GRID BODY
      ══════════════════════════════════════════════════════════════════════ */}
      <div style={{
        flex: 1, minHeight: 0,
        display: 'grid',
        gridTemplateColumns: '220px 1fr 320px',
        gridTemplateRows: '1fr 260px',
        overflow: 'hidden',
      }}>

        {/* ── LEFT SIDEBAR (col 1, rows 1-2) ──────────────────────────── */}
        <div style={{
          gridColumn: '1', gridRow: '1 / 3',
          borderRight: panelBorder, background: sidebarBg,
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>

          {/* Layout Loader */}
          <div style={{ flexShrink: 0 }}>
            <div style={sectionHeaderStyle}><span>Layout Loader</span></div>
            <div style={{ padding: 8 }}>
              <LayoutLoader
                layouts={layoutState.availableLayouts}
                selectedLayout={layoutState.selectedLayoutName}
                onSelect={handleLayoutSelect}
                onUpload={handleLayoutUpload}
              />
            </div>
          </div>

          {/* Layers — grows to fill middle space */}
          {layoutState.layout ? (
            <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', borderTop: panelBorder }}>
              <div style={sectionHeaderStyle}><span>Layers</span></div>
              <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
                <LayerToggle layers={layerVisibility} onToggle={handleToggleLayer} />
              </div>
            </div>
          ) : (
            <div style={{ flex: 1 }} />
          )}

          {/* Properties — 260px, matches Agent Chat height */}
          <div style={{ flexShrink: 0, height: 260, borderTop: panelBorder }}>
            <SelectionPanel
              selectedId={selectedId}
              layout={layoutState.layout}
              graphData={layoutState.graphData}
              onClose={() => select(null, 'viewport')}
            />
          </div>
        </div>

        {/* ── CENTER (col 2, row 1) ─────────────────────────────────────── */}
        <div style={{ gridColumn: '2', gridRow: '1', position: 'relative', overflow: 'hidden', minWidth: 0, minHeight: 0 }}>
          <div style={swapStyle}>
            {displayMode === 'geometry' ? (
              viewportProps ? (
                <div style={{ width: '100%', height: '100%', position: 'relative' }}>
                  <ThreeViewport {...viewportProps} />
                  {layoutState.isPending && (
                    <ProposalBanner onAccept={layoutState.acceptPending} onReject={layoutState.rejectPending} />
                  )}
                </div>
              ) : (
                <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, color: colors.muted, fontSize: 12 }}>
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke={colors.accentDim} strokeWidth="1.5">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                    <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                    <line x1="12" y1="22.08" x2="12" y2="12" />
                  </svg>
                  <span>Select or upload a layout to begin</span>
                </div>
              )
            ) : (
              <GraphPanel graphData={layoutState.graphData} selectedId={selectedId} onSelect={handleGraphSelect} showLabels={showLabels} isAgentRunning={agentState.isAgentRunning} fullscreen />
            )}
          </div>
        </div>

        {/* ── RIGHT PANEL (col 3, row 1) ────────────────────────────────── */}
        <div style={{
          gridColumn: '3', gridRow: '1 / 3',
          borderLeft: panelBorder, background: sidebarBg,
          display: 'grid',
          gridTemplateRows: '1fr 1fr 260px',
          overflow: 'hidden', minHeight: 0,
        }}>

          {/* Row 1 — Spatial Graph (~29%) */}
          <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', borderBottom: panelBorder, minHeight: 0 }}>
            <div style={sectionHeaderStyle}>
              <span>{displayMode === 'geometry' ? 'Spatial Graph' : '3D View'}</span>
            </div>
            <div style={{ flex: 1, position: 'relative', overflow: 'hidden', minHeight: 0 }}>
              <div style={swapStyle}>
                {displayMode === 'geometry' ? (
                  <GraphPanel graphData={layoutState.graphData} selectedId={selectedId} onSelect={handleGraphSelect} showLabels={showLabels} isAgentRunning={agentState.isAgentRunning} />
                ) : (
                  viewportProps ? <ThreeViewport {...viewportProps} /> : noLayoutPlaceholder
                )}
              </div>
            </div>
          </div>

          {/* Row 2 — Analysis Dashboard (large) */}
          <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', borderBottom: panelBorder, minHeight: 0 }}>
            <div style={sectionHeaderStyle}><span>Analysis</span></div>
            <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
              <Dashboard scores={layoutState.scores} />
            </div>
          </div>

          {/* Row 3 — Pipeline (compact, scrollable) */}
          <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
            <div style={sectionHeaderStyle}><span>Pipeline</span></div>
            <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
              <ProcessPanel nodeStatuses={agentState.nodeStatuses} />
            </div>
          </div>
        </div>

        {/* ── BOTTOM CHAT STRIP (all cols, row 2) ──────────────────────── */}
        <div style={{
          gridColumn: '2', gridRow: '2',
          borderTop: panelBorder,
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          background: isDark ? 'rgba(11,7,20,0.98)' : 'rgba(250,251,253,0.98)',
        }}>
          <ChatPanel
            messages={agentState.messages}
            onSend={handleChatSend}
            isAgentRunning={agentState.isAgentRunning}
            onReset={handleChatReset}
            onCancel={handleChatCancel}
            checkpoint={agentState.checkpoint}
            onDecision={handleChatDecision}
            statusText={agentState.currentStatus}
          />
        </div>
      </div>

      {/* ── FLOATING AGENT LOG ─────────────────────────────────────────── */}
      <FloatingPanel
        id="log"
        title="Agent Log"
        icon={<IconLog />}
        defaultPosition={{ x: 240, y: 60 }}
        defaultSize={{ width: 400 }}
        visible={logOpen}
        zIndex={300}
        onFocus={() => {}}
      >
        <ReasoningLog
          entries={agentState.logEntries}
          visible={true}
          onToggle={() => setLogOpen(v => !v)}
          isRunning={agentState.isAgentRunning}
        />
      </FloatingPanel>
    </div>
  );
}
