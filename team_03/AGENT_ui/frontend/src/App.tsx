import React, { useState, useEffect, useCallback, useRef } from 'react';
import ThreeViewport from './components/ThreeViewport/ThreeViewport';
import ProposalBanner from './components/ThreeViewport/ProposalBanner';
import LayerToggle from './components/LayerToggle';
import GraphPanel from './components/GraphPanel/GraphPanel';
import ChatPanel from './components/ChatPanel/ChatPanel';
import Dashboard from './components/Dashboard/Dashboard';
import ProcessPanel from './components/ProcessPanel/ProcessPanel';
import LayoutLoader from './components/LayoutLoader/LayoutLoader';
import VersionHistory from './components/VersionHistory/VersionHistory';
import AILayoutGenerator from './components/AILayoutGenerator';
import SelectionPanel from './components/ThreeViewport/SelectionPanel';
import ReasoningLog from './components/ReasoningLog/ReasoningLog';
import ThemeToggle, { useTheme } from './components/common/ThemeToggle';
import FloatingPanel from './components/common/FloatingPanel';
import { useWebSocket } from './hooks/useWebSocket';
import { useSelectionSync } from './hooks/useSelectionSync';
import { useLayoutState } from './hooks/useLayoutState';
import { useAgentState } from './hooks/useAgentState';
import type { ViewAction } from './hooks/useAgentState';
import WelcomePage from "./components/WelcomePage";
import OnboardingPage, { OnboardingData, LAYOUT_STATUS, WORKFLOWS } from "./components/OnboardingPage";
import type { LayerVisibility, LayerName } from './types';
import type { GridViz } from './components/ThreeViewport/CollisionOverlay';
import type { OrientationResult } from './components/ThreeViewport/OrientationOverlay';
import type { OverlayToggles, OverlayLoadStatus } from './components/Dashboard/Dashboard';

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
  const [showLabels, setShowLabels] = useState(false);  // shared: 3D labels + graph labels
  const [layoutFitSignal, setLayoutFitSignal] = useState(0);  // bumps only on explicit layout pick → triggers viewport fit-to-screen
  const [isovist, setIsovist] = useState<[number, number][] | null>(null);  // visibility surface from set_observer
  const [agentObserver, setAgentObserver] = useState<{ mode: 'person' | 'path'; point?: [number, number]; path?: [number, number][] } | null>(null);  // observer placed by the chat agent
  const [analyzing, setAnalyzing] = useState(false);          // Analysis Dashboard "Analyze" button in flight
  const [dashboardFocus, setDashboardFocus] = useState<string | null>(null); // gauge highlighted by chat view chips
  const [viewMode, setViewMode] = useState<ViewMode>('geometry');
  const [displayMode, setDisplayMode] = useState<ViewMode>('geometry');
  const [animPhase, setAnimPhase] = useState<'idle' | 'out' | 'in'>('idle');
  const [logOpen, setLogOpen] = useState(false);
  const [collisionOverlay, setCollisionOverlay] = useState<GridViz | null>(null);
  const [orientationOverlay, setOrientationOverlay] = useState<OrientationResult[] | null>(null);
  const [overlayLoadStatus, setOverlayLoadStatus] = useState<OverlayLoadStatus>({
    collision:  { state: 'idle' },
    visibility: { state: 'idle' },
    path:       { state: 'idle' },
  });
  const [generatorMode, setGeneratorMode] = useState(false);   // left panel → AI Layout Generator
  const [memState, setMemState] = useState<'idle' | 'confirm' | 'cleared'>('idle'); // Clear-memory button
  const [chatPanelHeight, setChatPanelHeight] = useState(260);
  const [isDraggingChat, setIsDraggingChat] = useState(false);
  const animTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const memTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wasRunningRef = useRef(false);
  // Holds the ThreeViewport's runAnalysis fn when a person/path observer is set.
  const runObserverRef = useRef<(() => void) | null>(null);
  const [observerReady, setObserverReady] = useState(false);
  const dragStartYRef = useRef<number>(0);
  const dragStartHRef = useRef<number>(0);

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
      case 'observer_result': {
        const ao = msg.status === 'ok' ? (msg.agentObserver ?? null) : null;
        setIsovist(msg.status === 'ok' ? msg.isovist : null);
        setAgentObserver(ao);
        if (ao && viewMode === 'graph') switchMode('geometry');
        // Transition visibility loading state → active or error (only once, not on every live drag frame).
        setOverlayLoadStatus(prev => {
          if (prev.visibility.state === 'loading') {
            return {
              ...prev,
              visibility: msg.status === 'ok' && msg.isovist
                ? { state: 'active' }
                : { state: 'error', message: 'Visibility computation returned no data' },
            };
          }
          return prev; // already active (live drag) — don't overwrite
        });
        break;
      }
      case 'analysis_overlay': {
        if (msg.kind === 'collision' && msg.grid_viz) {
          setCollisionOverlay(msg.grid_viz);
          if (viewMode !== 'geometry') switchMode('geometry');
        } else if (msg.kind === 'orientation' && msg.results) {
          setOrientationOverlay(msg.results);
          if (viewMode !== 'geometry') switchMode('geometry');
        }
        break;
      }
      case 'version_saved': {
        // A revision was saved (e.g. after Approve layout) → refresh the Version
        // History list and switch the viewport to the newly-saved version.
        // Use msg.name (from the backend) to avoid stale-closure on fetchVersions.
        const vName = msg.name ?? layoutState.selectedLayoutName;
        (async () => {
          if (vName) await layoutState.fetchVersions(vName);
          if (msg.id) {
            await layoutState.selectVersion(msg.id, msg.file);
            setLayoutFitSignal(n => n + 1);
          }
        })();
        break;
      }
    }
  };
  useEffect(() => ws.subscribe((msg) => dispatchRef.current(msg)), [ws]);

  // ── Auto-load layout ──────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      await layoutState.fetchLayouts();
      // loadLayout now fetches versions internally using the local name variable,
      // avoiding the stale-selectedLayoutName closure problem.
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

  useEffect(() => () => {
    if (animTimerRef.current) clearTimeout(animTimerRef.current);
    if (memTimerRef.current) clearTimeout(memTimerRef.current);
  }, []);

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

  const handleChatDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDraggingChat(true);
    dragStartYRef.current = e.clientY;
    dragStartHRef.current = chatPanelHeight;

    const onMove = (ev: MouseEvent) => {
      const delta = dragStartYRef.current - ev.clientY;
      const next = Math.min(600, Math.max(180, dragStartHRef.current + delta));
      setChatPanelHeight(next);
    };

    const onUp = () => {
      setIsDraggingChat(false);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [chatPanelHeight]);

  const handleLayoutSelect = useCallback(async (name: string) => {
    setIsovist(null);
    setCollisionOverlay(null);
    setOrientationOverlay(null);
    setOverlayLoadStatus({ collision: { state: 'idle' }, visibility: { state: 'idle' }, path: { state: 'idle' } });
    await layoutState.loadLayout(name);
    setLayoutFitSignal(n => n + 1);
  }, [layoutState]);

  // Version History — travel to a saved revision (or the original).
  const handleVersionSelect = useCallback(async (versionId: string, file: string | null) => {
    setIsovist(null);
    await layoutState.selectVersion(versionId, file);
    setLayoutFitSignal(n => n + 1);
  }, [layoutState]);

  // A revision was deleted from disk — refresh the list and, if the deleted
  // version was the active one, fall back to the most recent remaining version.
  const handleVersionDeleted = useCallback(async (deletedId: string) => {
    const name = layoutState.selectedLayoutName;
    if (!name) return;
    const fresh = await layoutState.fetchVersions(name);
    // If we just deleted the currently-viewed version, switch to the last one.
    if (deletedId === layoutState.selectedVersionId && fresh.length > 0) {
      const last = fresh[fresh.length - 1];
      await layoutState.selectVersion(last.id, last.file);
      setLayoutFitSignal(n => n + 1);
    }
  }, [layoutState]);

  const handleLayoutUpload = useCallback(async (file: File) => {
    await layoutState.uploadLayout(file);
    setLayoutFitSignal(n => n + 1);   // user uploaded → fit to screen
  }, [layoutState]);

  // ── AI Layout Generator ────────────────────────────────────────────────
  // Preview a candidate in the viewport (null restores the committed layout).
  const handleGeneratorPreview = useCallback((l: typeof layoutState.layout) => {
    if (l) layoutState.previewLayout(l);
    else layoutState.endPreview();
  }, [layoutState]);

  // Persist a candidate to AI_GENERATED + load it as active (panel stays open so
  // the user can keep several). Returns the saved name (or null on failure).
  const handleGeneratorSave = useCallback(async (name: string, l: NonNullable<typeof layoutState.layout>) => {
    const saved = await layoutState.saveAndLoadGenerated(name, l);
    if (saved) setLayoutFitSignal(n => n + 1);
    return saved;
  }, [layoutState]);

  // Close the generator → restore the committed (last accepted) layout, exit mode.
  const handleGeneratorClose = useCallback(() => {
    layoutState.endPreview();
    setGeneratorMode(false);
  }, [layoutState]);

  // Clear ALL agent memory (team_03/memory/*.md) — two-click confirm in the nav.
  const handleClearMemory = useCallback(async () => {
    if (memTimerRef.current) clearTimeout(memTimerRef.current);
    if (memState !== 'confirm') {
      setMemState('confirm');
      memTimerRef.current = setTimeout(() => setMemState('idle'), 3000);
      return;
    }
    setMemState('idle');
    try { await fetch('/api/memory', { method: 'DELETE' }); } catch { /* ignore */ }
    setMemState('cleared');
    memTimerRef.current = setTimeout(() => setMemState('idle'), 1800);
  }, [memState]);

  // Deterministic analysis of the currently-displayed layout → populates the
  // Analysis Dashboard without needing the LLM/MCP agent to run the tools.
  const handleAnalyze = useCallback(async () => {
    if (!layoutState.layout || analyzing) return;
    setAnalyzing(true);
    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ layout: layoutState.layout }),
      });
      if (res.ok) {
        const data = await res.json();
        layoutState.setScores(data);
        // Render overlays in the 3D viewport if analysis produced grid data.
        if (data.collision_overlay) setCollisionOverlay(data.collision_overlay);
        if (data.orientation_overlay?.results?.length) setOrientationOverlay(data.orientation_overlay.results);
        if (viewMode !== 'geometry' && (data.collision_overlay || data.orientation_overlay)) {
          switchMode('geometry');
        }
      }
    } catch {
      // ignore — leave the dashboard as-is on failure
    } finally {
      setAnalyzing(false);
    }
  }, [layoutState, analyzing, viewMode, switchMode]);

  // ── Overlay toggles (Visibility · Paths · Collision) in the Dashboard ────
  const overlayToggles: OverlayToggles = {
    collision:  collisionOverlay !== null,
    visibility: isovist !== null,
    path:       dashboardFocus === 'path',
  };

  const setToolStatus = useCallback((key: keyof OverlayToggles, state: OverlayLoadStatus[keyof OverlayToggles]['state'], message?: string) => {
    setOverlayLoadStatus(prev => ({ ...prev, [key]: { state, ...(message ? { message } : {}) } }));
  }, []);

  const handleToggleOverlay = useCallback(async (key: keyof OverlayToggles) => {
    if (!layoutState.layout) {
      setToolStatus(key, 'error', 'No layout loaded');
      return;
    }

    if (key === 'collision') {
      if (collisionOverlay) {
        setCollisionOverlay(null);
        setToolStatus('collision', 'idle');
      } else {
        setToolStatus('collision', 'loading');
        try {
          const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ layout: layoutState.layout, tool: 'collision' }),
          });
          if (!res.ok) throw new Error(`Server error ${res.status}`);
          const data = await res.json();
          if (data.collision_overlay) {
            setCollisionOverlay(data.collision_overlay);
            setToolStatus('collision', 'active');
            if (viewMode !== 'geometry') switchMode('geometry');
          } else {
            // Analysis ran OK but no violations — not an error
            setToolStatus('collision', 'idle', 'No clearance violations detected');
          }
        } catch (e) {
          setToolStatus('collision', 'error', e instanceof Error ? e.message : 'Collision analysis failed');
        }
      }

    } else if (key === 'visibility') {
      if (isovist) {
        setIsovist(null);
        setToolStatus('visibility', 'idle');
      } else {
        if (!runObserverRef.current) {
          setToolStatus('visibility', 'error', 'Place a person or path in the viewport first');
          return;
        }
        // Status goes loading → active/error when observer_result arrives (async WS)
        setToolStatus('visibility', 'loading');
        runObserverRef.current();
      }

    } else if (key === 'path') {
      if (dashboardFocus === 'path') {
        setDashboardFocus(null);
        setToolStatus('path', 'idle');
      } else {
        setToolStatus('path', 'loading');
        try {
          const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ layout: layoutState.layout, tool: 'path' }),
          });
          if (!res.ok) throw new Error(`Server error ${res.status}`);
          setDashboardFocus('path');
          setToolStatus('path', 'active');
        } catch (e) {
          setDashboardFocus(null);
          setToolStatus('path', 'error', e instanceof Error ? e.message : 'Path analysis failed');
        }
      }
    }
  }, [layoutState.layout, collisionOverlay, isovist, dashboardFocus, viewMode, switchMode, setToolStatus]);

  // Chat viewport controls — the UI equivalent of the terminal's checkpoint
  // toggles (1=BEFORE, 2=AFTER, 3/4/5=collision/visibility/paths, 0=clear).
  // BEFORE/AFTER swap the 3D viewport's layout; the analysis chips run the
  // deterministic analysis and highlight the matching Dashboard gauge.
  const handleView = useCallback(async (action: ViewAction) => {
    switch (action) {
      case 'before': {
        const name = layoutState.selectedLayoutName;
        if (name) {
          try {
            const res = await fetch(`/api/layouts/${encodeURIComponent(name)}`);
            if (res.ok) layoutState.previewLayout(await res.json());
          } catch { /* ignore — keep current view */ }
        }
        if (viewMode !== 'geometry') switchMode('geometry');
        break;
      }
      case 'after':
        layoutState.endPreview();
        if (viewMode !== 'geometry') switchMode('geometry');
        break;
      case 'collision':
      case 'visibility':
      case 'path':
        setDashboardFocus(action);
        await handleAnalyze();
        break;
      case 'clear':
        layoutState.endPreview();
        setDashboardFocus(null);
        setIsovist(null);
        setCollisionOverlay(null);
        setOrientationOverlay(null);
        setOverlayLoadStatus({ collision: { state: 'idle' }, visibility: { state: 'idle' }, path: { state: 'idle' } });
        break;
    }
  }, [layoutState, viewMode, switchMode, handleAnalyze]);

  const handleViewportSelect = useCallback((id: string | null) => { select(id, 'viewport'); }, [select]);
  const handleGraphSelect    = useCallback((id: string | null) => { select(id, 'graph'); }, [select]);

  const handleObserverPoint = useCallback((x: number, y: number, height: number, pointStr: string, live?: boolean) => {
    ws.send({ type: 'observer_point', x, y, height, point_str: pointStr, ...(live ? { live: true } : {}) });
  }, [ws]);

  const handleObserverPath = useCallback((points: Array<{ x: number; y: number }>) => {
    const path_str = points.map(p => `${p.x.toFixed(3)},${p.y.toFixed(3)}`).join(';');
    ws.send({ type: 'observer_path', path_str, height: 1.7 });
  }, [ws]);

  // ── Auth gates ────────────────────────────────────────────────────────────
  if (!loggedIn) return <WelcomePage onEnter={() => setLoggedIn(true)} />;
  if (!onboarded) return <OnboardingPage onComplete={(data) => {
    // The onboarding screens stand in for the first two pipeline nodes — mark
    // them completed (space_type_agent only if the Space step wasn't skipped).
    const done = ['profile_agent'];
    if (!data.skippedSpaceAgent && (data.layoutStatus || data.workflowType)) done.push('space_type_agent');
    agentState.markNodesCompleted(done);
    // Persist the profile as a global user-memory file (labels, not ids).
    const layoutStatusLabel = LAYOUT_STATUS.find(l => l.id === data.layoutStatus)?.label ?? data.layoutStatus;
    const workflowLabel = data.workflowType === 'custom'
      ? (data.workflowCustom || 'Custom')
      : (WORKFLOWS.find(w => w.id === data.workflowType)?.label ?? data.workflowType);
    fetch('/api/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        role: data.role, experience: data.experience, name: data.name,
        layoutStatus: layoutStatusLabel, workflowType: workflowLabel,
        workflowCustom: data.workflowCustom, spaceNotes: data.spaceNotes,
        skippedSpaceAgent: data.skippedSpaceAgent,
      }),
    }).catch(() => {});
    setOnboardingData(data);
    setOnboarded(true);
  }} />;

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
    isovist,
    agentObserver,
    onObserverChanged: () => { setIsovist(null); setAgentObserver(null); },
    showLabels,
    onToggleLabels: () => setShowLabels(v => !v),
    isAgentRunning: agentState.isAgentRunning,
    fitSignal: layoutFitSignal,
    collisionOverlay,
    orientationOverlay,
    onRegisterRunObserver: (fn: (() => void) | null) => {
      runObserverRef.current = fn;
      setObserverReady(fn !== null);
    },
    liveVisibility: isovist !== null,
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
              fontSize: 8, letterSpacing: '0.32em', color: isDark ? 'rgba(167,139,250,0.55)' : colors.muted,
              textTransform: 'uppercase', fontFamily: colors.fontHeading,
            }}>AIA Studio 2026</span>
            <span style={{
              fontSize: 14, fontWeight: 700, letterSpacing: '0.18em', color: isDark ? '#e9d5ff' : colors.accent,
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

        {/* Right: Clear memory + Log + WS dot + Theme */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={handleClearMemory}
            title="Delete ALL agent memory (learned rules + onboarding profile). The agent starts fresh."
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '3px 8px', borderRadius: 6,
              border: `1px solid ${memState === 'confirm' ? colors.error + '55' : memState === 'cleared' ? colors.success + '55' : 'transparent'}`,
              fontSize: 10, fontWeight: 500, letterSpacing: '0.04em', textTransform: 'uppercase',
              cursor: 'pointer', fontFamily: colors.font, transition: 'all 0.2s',
              background: memState === 'confirm' ? colors.error + '18' : memState === 'cleared' ? colors.success + '18' : 'transparent',
              color: memState === 'confirm' ? colors.error : memState === 'cleared' ? colors.success : colors.muted,
            }}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              <line x1="10" y1="11" x2="10" y2="17" /><line x1="14" y1="11" x2="14" y2="17" />
            </svg>
            {memState === 'confirm' ? 'Clear all?' : memState === 'cleared' ? 'Cleared' : 'Memory'}
          </button>
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
        gridTemplateColumns: '320px 1fr 320px',
        gridTemplateRows: `1fr ${chatPanelHeight}px`,
        overflow: 'hidden',
      }}>

        {/* ── LEFT SIDEBAR (col 1, rows 1-2) ──────────────────────────── */}
        <div style={{
          gridColumn: '1', gridRow: '1 / 3',
          borderRight: panelBorder, background: sidebarBg,
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>

          {generatorMode ? (
            <AILayoutGenerator
              onPreview={handleGeneratorPreview}
              onSave={handleGeneratorSave}
              onClose={handleGeneratorClose}
            />
          ) : (
          <>
          {/* Layout Loader */}
          <div style={{ flexShrink: 0 }}>
            <div style={sectionHeaderStyle}><span>Layout Loader</span></div>
            <div style={{ padding: 8 }}>
              <LayoutLoader
                layouts={layoutState.availableLayouts}
                selectedLayout={layoutState.selectedLayoutName}
                onSelect={handleLayoutSelect}
              />
              {/* AI Layout Generator launcher — swaps the whole left panel */}
              <button
                onClick={() => setGeneratorMode(true)}
                disabled={agentState.isAgentRunning}
                title={agentState.isAgentRunning ? 'Unavailable while the agent is running' : 'Generate floor plans with AI'}
                style={{
                  width: '100%', marginTop: 4, padding: '9px 12px', borderRadius: 8,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  cursor: agentState.isAgentRunning ? 'not-allowed' : 'pointer',
                  background: agentState.isAgentRunning ? colors.inputBg : colors.accentDim,
                  border: `1px solid ${agentState.isAgentRunning ? colors.border : colors.accent}`,
                  color: agentState.isAgentRunning ? colors.muted : colors.accent,
                  fontSize: 12, fontWeight: 600, fontFamily: colors.font,
                  letterSpacing: '0.04em', transition: 'all 0.15s',
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 3v4M3 5h4M6 17v4M4 19h4M13 3l2.5 6.5L22 12l-6.5 2.5L13 21l-2.5-6.5L4 12l6.5-2.5z" />
                </svg>
                AI Layout Generator
              </button>
            </div>
          </div>

          {/* Version History — overflow:visible so the absolute dropdown escapes
              the sidebar's overflow:hidden clip. */}
          {layoutState.layout && (
            <div style={{ flexShrink: 0, borderTop: panelBorder, overflow: 'visible', position: 'relative' }}>
              <div style={sectionHeaderStyle}>
                <span>Version History</span>
                {layoutState.versions.length > 0 && (
                  <span style={{ color: colors.accent, fontWeight: 700 }}>{layoutState.versions.length}</span>
                )}
              </div>
              <VersionHistory
                versions={layoutState.versions}
                selectedVersionId={layoutState.selectedVersionId}
                layoutName={layoutState.selectedLayoutName}
                onSelect={handleVersionSelect}
                onDeleted={handleVersionDeleted}
                disabled={agentState.isAgentRunning}
              />
            </div>
          )}

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
          </>
          )}
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
              <Dashboard
                scores={layoutState.scores}
                focusMetric={dashboardFocus}
                overlayToggles={overlayToggles}
                overlayLoadStatus={overlayLoadStatus}
                onToggleOverlay={handleToggleOverlay}
                observerReady={observerReady}
              />
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

        {/* ── BOTTOM CHAT STRIP (resizable) ───────────────────────────── */}
        <div
          style={{
            gridColumn: '2', gridRow: '2',
            display: 'flex', flexDirection: 'column', overflow: 'hidden',
            background: isDark ? 'rgba(20,14,35,0.99)' : 'rgba(238,234,248,0.98)',
            position: 'relative',
            height: chatPanelHeight,
            minHeight: 180,
            maxHeight: 600,
            transition: isDraggingChat ? 'none' : 'height 0.15s ease',
            boxShadow: isDark
              ? '0 -2px 16px rgba(139,92,246,0.08), inset 0 1px 0 rgba(139,92,246,0.15)'
              : '0 -2px 20px rgba(139,92,246,0.18), inset 0 1px 0 rgba(139,92,246,0.35)',
            borderTop: `1px solid ${isDark ? 'rgba(139,92,246,0.2)' : 'rgba(139,92,246,0.4)'}`,
          }}
        >
          {/* Drag handle — hover over top edge to resize */}
          <div
            onMouseDown={handleChatDragStart}
            style={{
              position: 'absolute', top: 0, left: 0, right: 0,
              height: 6, cursor: 'ns-resize', zIndex: 10,
              background: 'transparent',
              transition: 'background 0.2s',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = colors.accent + '33')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          />
          <ChatPanel
            messages={agentState.messages}
            onSend={handleChatSend}
            isAgentRunning={agentState.isAgentRunning}
            onReset={handleChatReset}
            onCancel={handleChatCancel}
            checkpoint={agentState.checkpoint}
            onDecision={handleChatDecision}
            statusText={agentState.currentStatus}
            ws={ws}
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
