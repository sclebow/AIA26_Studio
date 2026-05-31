import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import ChatThread from "../ui/ChatThread.jsx";
import TopBar from "../ui/TopBar.jsx";
import ErrorBoundary from "../ui/ErrorBoundary.jsx";
import ProfilePanel from "../components/ProfilePanel.jsx";
import Capabilities from "../components/Capabilities.jsx";
import SensePlan from "../canvas/SensePlan.jsx";
import SenseKey from "../components/SenseKey.jsx";
import FocusCard from "../components/FocusCard.jsx";
import LayerToggles from "../components/LayerToggles.jsx";
import Legend from "../components/Legend.jsx";
import TimelineStrip from "../components/TimelineStrip.jsx";
import LayoutPicker from "../components/LayoutPicker.jsx";
import SenseMixer from "../components/SenseMixer.jsx";
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
const DEFAULT_LAYERS = { plan: true, comfort: true, graph: false };

// What each lens needs computed before it can show anything real. The graph needs
// the TOPOLOGY node to have run (its NetworkX metrics drive the whole view).
const LAYER_REQUIRES = { plan: null, comfort: "scores", graph: "topology" };
// If a lens isn't available yet, clicking it asks Sensi to run the analysis.
const LAYER_RUN_MSG = { comfort: "analyse the layout", graph: "map the topology of the layout" };

export default function LayoutModeScreen({ messages, turns, thinking, persona, layoutId, layoutVersion = 0, onSend }) {
  const [chatOpen,     setChatOpen]     = useState(true);
  const [profileOpen,  setProfileOpen]  = useState(false);
  const [capOpen,      setCapOpen]      = useState(false);
  const [galaxyOpen,   setGalaxyOpen]   = useState(false);
  const [activeTurnId, setActiveTurnId] = useState(null);
  const [spaceInput,   setSpaceInput]   = useState(null);
  const [draft,        setDraft]        = useState("");
  const [layers,       setLayers]       = useState(DEFAULT_LAYERS);
  const taRef = useRef(null);

  const { focusSense, toggleSense, activeRoom, setActiveRoom } = useSelection();

  const latestTurn = turns.length ? turns[turns.length - 1] : null;
  const activeTurn = activeTurnId ? turns.find(t => t.id === activeTurnId) : latestTurn;

  useEffect(() => { if (latestTurn?.scores_json) setActiveTurnId(null); }, [latestTurn?.id]); // eslint-disable-line

  // auto-focus the worst room when a fresh analysis lands
  useEffect(() => {
    const rs = roomScores(activeTurn);
    if (rs.length) setActiveRoom(rs.reduce((a, b) => ((a.overallScore || 1) <= (b.overallScore || 1) ? a : b)).roomName);
  }, [activeTurn?.id]); // eslint-disable-line

  // auto-reveal the topology graph when a topology turn lands (its data is fresh,
  // and graph lenses are mutually exclusive so flow steps aside).
  useEffect(() => {
    if (activeTurn?.action === "topologic") setLayers((l) => ({ ...l, graph: true }));
  }, [activeTurn?.id]); // eslint-disable-line

  const rooms         = roomScores(activeTurn);
  const avg           = layoutScore(rooms);
  const conflicts     = conflictCount(activeTurn);
  const ringClass     = avg == null ? "" : avg >= 0.65 ? "score-pass" : avg >= 0.45 ? "score-warn" : "score-fail";
  const initial       = persona?.name?.charAt(0).toUpperCase() || "";
  const metrics       = layers.graph ? activeTurn?.graph_data?.metrics : null;

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
              <ChatThread messages={messages} thinking={thinking} format={formatChatMessage} />
              <div className="lm-input-area">
                <button className={"cap-btn" + (capOpen ? " on" : "")} onClick={() => setCapOpen(o => !o)} title="capabilities">⊞</button>
                <div className="send-row" style={{ flex: 1 }}>
                  <textarea ref={taRef} className="sensi-input" placeholder="ask sensi about your layout…" value={draft}
                    onChange={e => { setDraft(e.target.value); e.target.style.height = "50px"; e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px"; }}
                    onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
                  <button className="btn-send" onClick={() => send()}>→</button>
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
            <SenseMixer />
            <LayerToggles layers={layers} onToggle={onLayer} available={layerAvailable} />
            <button className="layer-pill" title="3D relationship galaxy"
              onClick={() => rooms.length ? setGalaxyOpen(true) : onSend("analyse the layout")}>galaxy ↗</button>
          </div>

          <div className="lm-viewer">
            <SensePlan rooms={rooms} layoutId={layoutId} layoutVersion={layoutVersion} layers={layers} graphData={activeTurn?.graph_data} />

            {/* topology metric pills */}
            {metrics && (
              <div className="metric-pills">
                {metrics.most_connected && metrics.most_connected !== "none" && <span className="metric-pill">hub · {metrics.most_connected}</span>}
                {metrics.bridge_rooms?.length > 0 && <span className="metric-pill">bridges · {metrics.bridge_rooms.join(", ")}</span>}
                {metrics.isolated_rooms?.length > 0 && <span className="metric-pill warn">isolated · {metrics.isolated_rooms.join(", ")}</span>}
                {metrics.num_components > 1 && <span className="metric-pill warn">detached · {metrics.num_components} zones</span>}
              </div>
            )}

            {/* legend (corner) */}
            <div className="legend-corner"><Legend layers={layers} /></div>

            {/* docked sense-coupling key (universal model reference) */}
            <div className="sense-key-corner"><SenseKey rooms={rooms} /></div>

            {/* focus card (right overlay, on room select) */}
            <AnimatePresence>
              {activeRoom && rooms.length > 0 && (
                <FocusCard key="focus-card" turn={activeTurn} persona={persona} onClose={() => setActiveRoom(null)} onFix={send} />
              )}
            </AnimatePresence>
          </div>

          <TimelineStrip turns={turns} activeTurnId={activeTurnId}
            onSelect={(id) => setActiveTurnId(id === activeTurnId ? null : id)} />
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
