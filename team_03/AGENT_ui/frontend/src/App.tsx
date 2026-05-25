import React, { useState, useEffect, useCallback, useRef } from 'react';
import ThreeViewport from './components/ThreeViewport/ThreeViewport';
import ProposalBanner from './components/ThreeViewport/ProposalBanner';
import LayerToggle from './components/LayerToggle';
import GraphPanel from './components/GraphPanel/GraphPanel';
import ChatPanel from './components/ChatPanel/ChatPanel';
import Dashboard from './components/Dashboard/Dashboard';
import ProcessPanel from './components/ProcessPanel/ProcessPanel';
import LayoutLoader from './components/LayoutLoader/LayoutLoader';
import ReasoningLog from './components/ReasoningLog/ReasoningLog';
import ThemeToggle, { useTheme } from './components/common/ThemeToggle';
import FloatingPanel from './components/common/FloatingPanel';
import { useWebSocket } from './hooks/useWebSocket';
import { useSelectionSync } from './hooks/useSelectionSync';
import { useLayoutState } from './hooks/useLayoutState';
import { useAgentState } from './hooks/useAgentState';
import type { LayerVisibility, LayerName } from './types';

// ─── Defaults ────────────────────────────────────────────────────────────────

const defaultVisibility: LayerVisibility = {
  outline: true,
  rooms: true,
  doors: true,
  windows: true,
  furniture: true,
  mep: true,
  structure: true,
};

type ViewMode = 'geometry' | 'graph';

// ─── Panel visibility state ─────────────────────────────────────────────────

interface PanelVisibility {
  layout: boolean
  layers: boolean
  pipeline: boolean
  chat: boolean
  dashboard: boolean
  log: boolean
}

const defaultPanelVisibility: PanelVisibility = {
  layout: true,
  layers: true,
  pipeline: true,
  chat: true,
  dashboard: true,
  log: false,
};

// ─── Small SVG icons for panel headers ──────────────────────────────────────

const IconCube = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
  </svg>
);

const IconLayers = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polygon points="12 2 2 7 12 12 22 7 12 2" />
    <polyline points="2 17 12 22 22 17" />
    <polyline points="2 12 12 17 22 12" />
  </svg>
);

const IconPipeline = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </svg>
);

const IconChat = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const IconDashboard = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="3" width="7" height="7" rx="1" />
    <rect x="3" y="14" width="7" height="7" rx="1" />
    <rect x="14" y="14" width="7" height="7" rx="1" />
  </svg>
);

const IconLog = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
  </svg>
);

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';
  const ws = useWebSocket();
  const { selectedId, select } = useSelectionSync(ws);
  const layoutState = useLayoutState();
  const agentState = useAgentState({ onScoresReady: layoutState.setScores });
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(defaultVisibility);
  const [logVisible, setLogVisible] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('geometry');
  const [panels, setPanels] = useState<PanelVisibility>(defaultPanelVisibility);
  const [topZ, setTopZ] = useState(110);

  // Z-index state per panel
  const [panelZ, setPanelZ] = useState<Record<string, number>>({
    layout: 100, layers: 101, pipeline: 102,
    chat: 103, dashboard: 104, log: 105,
  });

  const bringToFront = useCallback((id: string) => {
    setTopZ(prev => {
      const next = prev + 1;
      setPanelZ(pz => ({ ...pz, [id]: next }));
      return next;
    });
  }, []);

  // ── WebSocket dispatcher ──────────────────────────────────────────────────
  useEffect(() => {
    if (!ws.lastMessage) return;
    const msg = ws.lastMessage;
    switch (msg.type) {
      case 'agent_event':    agentState.handleAgentEvent(msg);    break;
      case 'agent_response': agentState.handleAgentResponse(msg); break;
      case 'state_update':   layoutState.updateFromWS(msg);       break;
      case 'selection_sync': select(msg.elementId, msg.source);   break;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.lastMessage]);

  // ── Auto-load layout ──────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      await layoutState.fetchLayouts();
      if (!layoutState.layout) await layoutState.loadLayout('industrial_005');
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Poll layout from disk while agent is running ──────────────────────────
  const wasRunningRef = useRef(false);
  useEffect(() => {
    if (agentState.isAgentRunning && !layoutState.isPending) {
      wasRunningRef.current = true;
      const interval = setInterval(() => {
        layoutState.reloadLayout();
      }, 3000);
      return () => clearInterval(interval);
    } else if (wasRunningRef.current && !layoutState.isPending) {
      // Agent just finished — do a final reload to catch any last changes
      wasRunningRef.current = false;
      layoutState.reloadLayout();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentState.isAgentRunning, layoutState.isPending]);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleToggleLayer = useCallback((layer: LayerName) => {
    setLayerVisibility(prev => ({ ...prev, [layer]: !prev[layer] }));
  }, []);

  const handleChatSend = useCallback((content: string) => {
    agentState.addUserMessage(content);
    agentState.runDemoSimulation(content);
  }, [agentState]);

  const handleChatReset  = useCallback(() => { agentState.resetChat(); }, [agentState]);
  const handleChatCancel = useCallback(() => { agentState.cancelLast(); }, [agentState]);

  const handleLayoutSelect  = useCallback(async (name: string) => { await layoutState.loadLayout(name); }, [layoutState]);
  const handleLayoutUpload  = useCallback(async (file: File)   => { await layoutState.uploadLayout(file); }, [layoutState]);
  const handleViewportSelect = useCallback((id: string | null) => { select(id, 'viewport'); }, [select]);
  const handleGraphSelect    = useCallback((id: string | null) => { select(id, 'graph');    }, [select]);

  const togglePanel = useCallback((key: keyof PanelVisibility) => {
    setPanels(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // ── Computed positions (relative to window) ──────────────────────────────
  const W = typeof window !== 'undefined' ? window.innerWidth : 1920;
  const H = typeof window !== 'undefined' ? window.innerHeight : 1080;

  return (
    <div style={{
      position: 'relative',
      width: '100vw',
      height: '100vh',
      background: colors.bg,
      color: colors.text,
      fontFamily: colors.font,
      overflow: 'hidden',
    }}>

      {/* ═══════════════════════════════════════════════════════════════════════
          TOP NAV BAR
      ═══════════════════════════════════════════════════════════════════════ */}
      <div style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: 44,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        zIndex: 250,
        background: isDark ? 'rgba(18, 19, 26, 0.96)' : 'rgba(245, 245, 247, 0.97)',
        borderBottom: `1px solid ${colors.border}`,
      }}>
        {/* Left: Logo + Title */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 13,
          fontWeight: 600,
          color: colors.text,
          letterSpacing: '0.02em',
        }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={colors.accent} strokeWidth="2">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
            <line x1="12" y1="22.08" x2="12" y2="12" />
          </svg>
          AGENT Studio
        </div>

        {/* Center: View Mode Toggle */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)',
          borderRadius: 10,
          padding: 3,
          border: `1px solid ${colors.border}`,
        }}>
          <button
            onClick={() => setViewMode('geometry')}
            style={{
              padding: '5px 16px',
              borderRadius: 8,
              border: 'none',
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: '0.02em',
              cursor: 'pointer',
              fontFamily: colors.font,
              transition: 'all 0.2s',
              background: viewMode === 'geometry'
                ? (isDark ? 'rgba(139, 92, 246, 0.15)' : 'rgba(124, 58, 237, 0.12)')
                : 'transparent',
              color: viewMode === 'geometry' ? colors.accent : colors.muted,
            }}
          >
            3D Viewport
          </button>
          <button
            onClick={() => setViewMode('graph')}
            style={{
              padding: '5px 16px',
              borderRadius: 8,
              border: 'none',
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: '0.02em',
              cursor: 'pointer',
              fontFamily: colors.font,
              transition: 'all 0.2s',
              background: viewMode === 'graph'
                ? (isDark ? 'rgba(139, 92, 246, 0.15)' : 'rgba(124, 58, 237, 0.12)')
                : 'transparent',
              color: viewMode === 'graph' ? colors.accent : colors.muted,
            }}
          >
            Spatial Graph
          </button>
        </div>

        {/* Right: Panel toggles + Status + Theme */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Panel toggle pills */}
          {(['layout', 'layers', 'pipeline', 'chat', 'dashboard', 'log'] as (keyof PanelVisibility)[]).map(key => (
            <button
              key={key}
              onClick={() => togglePanel(key)}
              style={{
                padding: '3px 8px',
                borderRadius: 6,
                border: `1px solid ${panels[key] ? colors.accent + '30' : 'transparent'}`,
                fontSize: 9,
                fontWeight: 500,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                cursor: 'pointer',
                fontFamily: colors.font,
                transition: 'all 0.2s',
                background: panels[key] ? colors.accentDim : 'transparent',
                color: panels[key] ? colors.accent : colors.muted,
              }}
            >
              {key}
            </button>
          ))}

          {/* Connection dot */}
          <div style={{
            width: 6, height: 6, borderRadius: '50%',
            background: ws.isConnected ? colors.success : colors.error,
            boxShadow: ws.isConnected
              ? `0 0 6px ${colors.success}`
              : `0 0 6px ${colors.error}`,
          }} />

          <ThemeToggle />
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════════
          FULL-SCREEN VIEWPORT / GRAPH (toggle with display)
      ═══════════════════════════════════════════════════════════════════════ */}

      {/* 3D Viewport */}
      <div style={{
        position: 'absolute',
        inset: 0,
        paddingTop: 44,
        display: viewMode === 'geometry' ? 'block' : 'none',
      }}>
        {layoutState.layout ? (
          <>
            <ThreeViewport
              layout={layoutState.layout}
              selectedId={selectedId}
              onSelect={handleViewportSelect}
              layers={layerVisibility}
              graphData={layoutState.graphData}
              modifiedIds={layoutState.modifiedIds}
            />
            {layoutState.isPending && (
              <ProposalBanner
                onAccept={layoutState.acceptPending}
                onReject={layoutState.rejectPending}
              />
            )}
          </>
        ) : (
          <div style={{
            width: '100%',
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: colors.bg,
            color: colors.muted,
            fontSize: 13,
            flexDirection: 'column',
            gap: 12,
          }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none"
              stroke={colors.accentDim} strokeWidth="1.5">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
              <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
              <line x1="12" y1="22.08" x2="12" y2="12" />
            </svg>
            <span>Select or upload a layout to begin</span>
          </div>
        )}
      </div>

      {/* Graph Panel (full-screen background) */}
      <div style={{
        position: 'absolute',
        inset: 0,
        paddingTop: 44,
        display: viewMode === 'graph' ? 'block' : 'none',
      }}>
        <GraphPanel
          graphData={layoutState.graphData}
          selectedId={selectedId}
          onSelect={handleGraphSelect}
          fullscreen
        />
      </div>

      {/* ═══════════════════════════════════════════════════════════════════════
          FLOATING PANELS
      ═══════════════════════════════════════════════════════════════════════ */}

      {/* Layout Loader — static, not draggable */}
      <FloatingPanel
        id="layout"
        title="Layout"
        icon={<IconCube />}
        defaultPosition={{ x: 16, y: 56 }}
        defaultSize={{ width: 240 }}
        visible={panels.layout}
        zIndex={panelZ.layout}
        onFocus={() => bringToFront('layout')}
        draggable={false}
      >
        <LayoutLoader
          layouts={layoutState.availableLayouts}
          selectedLayout={layoutState.selectedLayoutName}
          onSelect={handleLayoutSelect}
          onUpload={handleLayoutUpload}
        />
      </FloatingPanel>

      {/* Layers — draggable, positioned to avoid Layout overlap */}
      {viewMode === 'geometry' && (
        <FloatingPanel
          id="layers"
          title="Layers"
          icon={<IconLayers />}
          defaultPosition={{ x: 270, y: 100 }}
          defaultSize={{ width: 150 }}
          visible={panels.layers}
          zIndex={panelZ.layers}
          onFocus={() => bringToFront('layers')}
          draggable={true}
        >
          <LayerToggle layers={layerVisibility} onToggle={handleToggleLayer} />
        </FloatingPanel>
      )}

      {/* Pipeline — static, not draggable */}
      <FloatingPanel
        id="pipeline"
        title="Pipeline"
        icon={<IconPipeline />}
        defaultPosition={{ x: 16, y: 460 }}
        defaultSize={{ width: 220 }}
        visible={panels.pipeline}
        zIndex={panelZ.pipeline}
        onFocus={() => bringToFront('pipeline')}
        draggable={false}
        maxHeight={350}
      >
        <ProcessPanel nodeStatuses={agentState.nodeStatuses} />
      </FloatingPanel>

      {/* Chat — static, not draggable */}
      <FloatingPanel
        id="chat"
        title="Chat"
        icon={<IconChat />}
        defaultPosition={{ x: W - 356, y: 56 }}
        defaultSize={{ width: 340, height: 380 }}
        visible={panels.chat}
        zIndex={panelZ.chat}
        onFocus={() => bringToFront('chat')}
        draggable={false}
      >
        <ChatPanel
          messages={agentState.messages}
          onSend={handleChatSend}
          isAgentRunning={agentState.isAgentRunning}
          onReset={handleChatReset}
          onCancel={handleChatCancel}
        />
      </FloatingPanel>

      {/* Dashboard — static, not draggable */}
      <FloatingPanel
        id="dashboard"
        title="Analysis"
        icon={<IconDashboard />}
        defaultPosition={{ x: W - 356, y: 450 }}
        defaultSize={{ width: 340 }}
        visible={panels.dashboard}
        zIndex={panelZ.dashboard}
        onFocus={() => bringToFront('dashboard')}
        draggable={false}
      >
        <Dashboard scores={layoutState.scores} />
      </FloatingPanel>

      {/* Reasoning Log */}
      <FloatingPanel
        id="log"
        title="Agent Log"
        icon={<IconLog />}
        defaultPosition={{ x: W - 420, y: H - 280 }}
        defaultSize={{ width: 400 }}
        visible={panels.log}
        zIndex={panelZ.log}
        onFocus={() => bringToFront('log')}
      >
        <ReasoningLog
          entries={agentState.logEntries}
          visible={true}
          onToggle={() => togglePanel('log')}
          isRunning={agentState.isAgentRunning}
        />
      </FloatingPanel>
    </div>
  );
}
