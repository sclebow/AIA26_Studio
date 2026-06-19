import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import ChatThread from "../ui/ChatThread.jsx";
import InteractiveMessage from "../ui/InteractiveMessage.jsx";
import TopBar from "../ui/TopBar.jsx";
import ErrorBoundary from "../ui/ErrorBoundary.jsx";
import ProfilePanel from "../components/ProfilePanel.jsx";
import Capabilities from "../components/Capabilities.jsx";
import SensePlan from "../canvas/SensePlan.jsx";
import SenseKey from "../components/SenseKey.jsx";
import FocusCard from "../components/FocusCard.jsx";
import LayerToggles from "../components/LayerToggles.jsx";
import Legend from "../components/Legend.jsx";
import CheckpointsStrip from "../components/CheckpointsStrip.jsx";
import LayoutPicker from "../components/LayoutPicker.jsx";
import { formatChatMessage } from "../lib/formatMessage.js";
import { useSelection } from "../lib/selection.jsx";
import { roomScores, conflictCount, layoutScore } from "../lib/turn.js";

// 3D galaxy is heavy (three.js) — lazy so it never enters the initial bundle.
const RelationshipGalaxy = lazy(() => import("../galaxy/RelationshipGalaxy.jsx"));
import { EASE } from "../lib/motion.js";

function SpaceInput({ pos, onSend, onClose }) {
  const [val, setVal] = useState("");
  const inputRef = useRef(null);
  useEffect(() => { inputRef.current?.focus(); }, []);
  const submit = () => { const t = val.trim(); if (!t) { onClose(); return; } onSend(t); onClose(); };
  return (
    <div className="space-input-wrap" style={{ left: pos.x, top: pos.y }} onMouseDown={e => e.stopPropagation()}>
      <textarea ref={inputRef} className="space-input-ta" placeholder="ask sensi…" value={val} rows={1}
        onChange={e => setVal(e.target.value)}
        onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } if (e.key === "Escape") onClose(); }} />
      <button className="space-input-send" onClick={submit}>→</button>
    </div>
  );
}

// Two-tier canvas model:
//   plan    — the architecture base (walls/rooms/openings/furniture). Toggle off
//             to isolate the graph on the bare field.
//   comfort — the comfort read-out (room fill tint + per-room score ring).
//   graph   — ONE unified room-relationship graph: nodes (rooms) + structural
//             adjacency + directional transmissive flow, all together. (Topology +
//             flow used to be two lenses; they are the same graph, now merged.)
const DEFAULT_LAYERS = { plan: true, comfort: true, graph: false, material: false };

// What each lens needs computed before it can show anything real. The graph needs
// the TOPOLOGY node to have run (its NetworkX metrics drive the whole view). The
// material lens is deterministic (reads floorMaterial straight off the layout), so
// it needs nothing pre-computed.
const LAYER_REQUIRES = { plan: null, comfort: "scores", graph: "topology", material: null };
// If a lens isn't available yet, clicking it asks Sensi to run the analysis.
const LAYER_RUN_MSG = { comfort: "analyse the layout", graph: "map the topology of the layout" };

export default function LayoutModeScreen({ messages, turns, thinking, persona, layoutId, layoutVersion = 0, onSend, onReport,
  streaming = false, onStop,
  checkpoints = [], hasUncommitted = false, uncommittedDelta = {}, onCommit, onRestore,
  viewedTurn = null, onViewCheckpoint, onClearView }) {
  const [chatOpen,     setChatOpen]     = useState(true);
  const [profileOpen,  setProfileOpen]  = useState(false);
  const [capOpen,      setCapOpen]      = useState(false);
  const [galaxyOpen,   setGalaxyOpen]   = useState(false);
  const [activeTurnId, setActiveTurnId] = useState(null);
  const [spaceInput,   setSpaceInput]   = useState(null);
  const [draft,        setDraft]        = useState("");
  const [layers,       setLayers]       = useState(DEFAULT_LAYERS);
  const taRef = useRef(null);
  const planRef = useRef(null);

  const { focusSense, toggleSense, activeRoom, setActiveRoom } = useSelection();

  const latestTurn = turns.length ? turns[turns.length - 1] : null;
  const activeTurn = activeTurnId ? turns.find(t => t.id === activeTurnId) : latestTurn;

  useEffect(() => { if (latestTurn?.scores_json) setActiveTurnId(null); }, [latestTurn?.id]); // eslint-disable-line

  // After an analysis, auto-focus the worst room; after an EDIT, focus the room you
  // just changed so its new scores are in front of you (not a jump to the worst room).
  useEffect(() => {
    const rs = roomScores(activeTurn);
    if (!rs.length) return;
    const edited = (activeTurn?.layout_diffs || []).find((d) => d?.room_name)?.room_name;
    if (activeTurn?.action === "edit" && edited && rs.some((r) => r.roomName === edited)) {
      setActiveRoom(edited);
    } else {
      setActiveRoom(rs.reduce((a, b) => ((a.overallScore || 1) <= (b.overallScore || 1) ? a : b)).roomName);
    }
  }, [activeTurn?.id]); // eslint-disable-line

  // auto-reveal the topology graph when a topology turn lands (its data is fresh,
  // and graph lenses are mutually exclusive so flow steps aside).
  useEffect(() => {
    if (activeTurn?.action === "topologic") setLayers((l) => ({ ...l, graph: true }));
  }, [activeTurn?.id]); // eslint-disable-line

  // panelTurn drives the score panel/canvas: a clicked checkpoint (read-only review)
  // overrides the live turn so the rings + FocusCard show that milestone's scores.
  const panelTurn     = viewedTurn || activeTurn;
  const rooms         = roomScores(panelTurn);
  // closed vocabulary for the chat linkifier — the current layout's room names.
  const roomNames     = rooms.map((r) => r.roomName).filter(Boolean);
  const avg           = layoutScore(rooms);
  const conflicts     = conflictCount(panelTurn);

  // Rooms whose overall score moved on the latest EDIT turn — pulsed on the canvas so
  // the change is felt. Suppressed while reviewing a checkpoint.
  const prevTurn      = turns.length > 1 ? turns[turns.length - 2] : null;
  const changedRooms  = useMemo(() => {
    if (viewedTurn || activeTurn?.action !== "edit") return new Set();
    const prevMap = {};
    roomScores(prevTurn).forEach((r) => { prevMap[r.roomName] = r.overallScore; });
    const s = new Set();
    roomScores(activeTurn).forEach((r) => {
      const p = prevMap[r.roomName];
      if (p == null || Math.abs((r.overallScore || 0) - (p || 0)) > 0.005) s.add(r.roomName);
    });
    return s;
  }, [activeTurn?.id, viewedTurn]); // eslint-disable-line
  const ringClass     = avg == null ? "" : avg >= 0.65 ? "score-pass" : avg >= 0.45 ? "score-warn" : "score-fail";
  const initial       = persona?.name?.charAt(0).toUpperCase() || "";

  const cursorPos = useRef({ x: 200, y: 200 });
  useEffect(() => {
    const onMove = e => { cursorPos.current = { x: e.clientX, y: e.clientY }; };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  // Space-to-talk: when the chat drawer is collapsed, Space opens a floating input.
  useEffect(() => {
    const onKey = e => {
      if (chatOpen) return;
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
      if (e.code === "Space") { e.preventDefault(); setSpaceInput({ x: cursorPos.current.x - 140, y: cursorPos.current.y - 24 }); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [chatOpen]);

  useEffect(() => {
    if (!spaceInput) return;
    const dismiss = () => setSpaceInput(null);
    const t = setTimeout(() => window.addEventListener("mousedown", dismiss), 10);
    return () => { clearTimeout(t); window.removeEventListener("mousedown", dismiss); };
  }, [spaceInput]);

  const send = useCallback((text) => {
    const t = (text || draft).trim();
    if (!t) return;
    setDraft("");
    if (taRef.current) taRef.current.style.height = "50px";
    onSend(t);
  }, [draft, onSend]);

  // Layer availability follows what's been computed.
  const dataReady = { scores: rooms.length > 0, topology: !!activeTurn?.graph_data?.nodes?.length };
  const layerAvailable = (k) => LAYER_REQUIRES[k] == null || dataReady[LAYER_REQUIRES[k]];
  const onLayer = (k) => {
    if (!layerAvailable(k)) { onSend(LAYER_RUN_MSG[k]); return; }   // click-to-run
    setLayers((l) => ({ ...l, [k]: !l[k] }));
  };

  return (
    <div className="layout-mode-screen">

      <TopBar wide>
        <span className="top-bar-sep">|</span>
        <span className="top-bar-act" title="you are shaping & exploring the layout">shape</span>
        <span className="top-bar-sep">|</span>
        <LayoutPicker layoutId={layoutId} onSelect={(id) => onSend(`load layout ${id}`)} onUpload={(id) => onSend(`analyse layout ${id}`)} />
        <div className="top-bar-status-group">
          {conflicts > 0 && <span className="top-bar-conflict-badge">{conflicts} {conflicts === 1 ? "conflict" : "conflicts"}</span>}
          {avg != null && <span className={"top-bar-score-ring " + ringClass}>{avg.toFixed(2)}</span>}
          {persona && initial && (
            <button className="top-bar-user-avatar" onClick={() => setProfileOpen(true)} title="your comfort profile">{initial}</button>
          )}
        </div>
      </TopBar>

      <Capabilities open={capOpen} onClose={() => setCapOpen(false)} />

      <div className="lm-body">

        <AnimatePresence>
          {chatOpen && (
            <motion.div className="lm-chat-sidebar"
              initial={{ x: -40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: -40, opacity: 0 }}
              transition={{ duration: 0.2, ease: EASE.out }}>
              <ChatThread messages={messages} thinking={thinking}
                renderMessage={(text) => <InteractiveMessage text={text} rooms={roomNames} />}
                hasUncommitted={hasUncommitted} uncommittedDelta={uncommittedDelta} onCommit={onCommit} />
              <div className="lm-input-area">
                <button className={"cap-btn" + (capOpen ? " on" : "")} onClick={() => setCapOpen(o => !o)} title="capabilities">⊞</button>
                <div className="send-row" style={{ flex: 1 }}>
                  <textarea ref={taRef} className="sensi-input" placeholder="ask sensi about your layout…" value={draft}
                    onChange={e => { setDraft(e.target.value); e.target.style.height = "50px"; e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px"; }}
                    onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); streaming ? onStop?.() : send(); } }} />
                  <button className="btn-send" onClick={() => (streaming ? onStop?.() : send())}
                    title={streaming ? "stop generating" : "send"}>{streaming ? "■" : "→"}</button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="lm-center">

          <div className="lm-center-controls">
            <button className="lm-chat-toggle" onClick={() => setChatOpen(o => !o)} title={chatOpen ? "hide chat" : "show chat (Space to talk)"}>
              {chatOpen ? "‹ chat" : "chat ›"}
            </button>
            <LayerToggles layers={layers} onToggle={onLayer} available={layerAvailable} />
            <span className="lm-controls-sep" aria-hidden="true" />
            <button className="layer-pill" title="3D relationship galaxy"
              onClick={() => rooms.length ? setGalaxyOpen(true) : onSend("analyse the layout")}>galaxy ↗</button>
            <button className="layer-pill lm-report-cta" title={hasUncommitted
                ? "open The Vision — shows your last committed checkpoint (commit to include new edits)"
                : "open The Vision — renders, prompts & scores per room"}
              onClick={() => rooms.length ? onReport?.() : onSend("analyse the layout")}>the vision →</button>
            {hasUncommitted && (
              <span className="lm-uncommitted-hint" title="The Vision renders committed checkpoints; commit your edits to include them"
                style={{ fontSize: 11, color: "rgba(var(--fg-rgb),0.55)", fontFamily: "var(--font-mono)" }}>
                · uncommitted edits not in The Vision yet
              </span>
            )}
          </div>

          {viewedTurn && (
            <div className="lm-viewing-banner" style={{
              position: "absolute", top: 44, left: "50%", transform: "translateX(-50%)", zIndex: 6,
              fontFamily: "var(--font-mono)", fontSize: 12, padding: "4px 10px", borderRadius: 8,
              background: "rgba(10,10,10,.85)", border: "1px solid rgba(var(--fg-rgb),.15)", color: "rgba(var(--fg-rgb),.8)",
            }}>
              viewing checkpoint · {viewedTurn.label}
              <button className="layer-pill" style={{ marginLeft: 8 }} onClick={() => onClearView?.()}>back to current ✕</button>
            </div>
          )}

          <div className={"lm-viewer" + (activeRoom && rooms.length > 0 ? " has-focus" : "")}>
            <SensePlan ref={planRef} rooms={rooms} layoutId={layoutId} layoutVersion={layoutVersion} layers={layers}
              graphData={panelTurn?.graph_data} diffs={viewedTurn ? [] : (activeTurn?.layout_diffs || [])}
              changedRooms={changedRooms} pulseKey={activeTurn?.id} />

            {/* reading-aids legend — a horizontal strip in the top canvas band,
                sharing the row with Expand All (card-less) */}
            <Legend layers={layers} />

            {/* sense-coupling key plan + filter, bottom-left (card-less) */}
            <div className="lm-corner-left">
              <SenseKey rooms={rooms} />
            </div>

            {/* focus card (right overlay, on room select — the plan reflows left for it) */}
            <AnimatePresence>
              {activeRoom && rooms.length > 0 && (
                <FocusCard key="focus-card" turn={panelTurn} persona={persona} onClose={() => setActiveRoom(null)} onFix={send} />
              )}
            </AnimatePresence>
          </div>

          <CheckpointsStrip checkpoints={checkpoints} onRestore={onRestore}
            onView={onViewCheckpoint} viewedId={viewedTurn ? viewedTurn.checkpointId : null} />
        </div>
      </div>

      {spaceInput && <SpaceInput pos={spaceInput} onSend={send} onClose={() => setSpaceInput(null)} />}
      <ProfilePanel persona={persona} open={profileOpen} onClose={() => setProfileOpen(false)} onFullView={() => setProfileOpen(false)} />

      {galaxyOpen && (
        <ErrorBoundary fallback={(err) => (
          <div className="galaxy-overlay galaxy-loading" style={{ flexDirection: "column", gap: 12 }}>
            <div>the galaxy hit an error</div>
            <div style={{ fontSize: 11, opacity: 0.6, maxWidth: 480, textAlign: "center", textTransform: "none", letterSpacing: 0 }}>{String(err?.message || err)}</div>
            <button className="galaxy-lv" onClick={() => setGalaxyOpen(false)}>close</button>
          </div>
        )}>
          <Suspense fallback={<div className="galaxy-overlay galaxy-loading">opening the galaxy…</div>}>
            <RelationshipGalaxy turn={activeTurn} persona={persona} onClose={() => setGalaxyOpen(false)} />
          </Suspense>
        </ErrorBoundary>
      )}
    </div>
  );
}
