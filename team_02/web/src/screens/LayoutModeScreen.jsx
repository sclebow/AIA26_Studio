import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import SensiAvatar from "../components/SensiAvatar.jsx";
import Thinking from "../components/Thinking.jsx";
import ProfilePanel from "../components/ProfilePanel.jsx";
import Capabilities from "../components/Capabilities.jsx";
import SensePlan from "../components/SensePlan.jsx";
import SenseGraph from "../components/SenseGraph.jsx";
import FocusCard from "../components/FocusCard.jsx";
import LayerToggles from "../components/LayerToggles.jsx";
import Legend from "../components/Legend.jsx";
import TimelineStrip from "../components/TimelineStrip.jsx";
import LayoutPicker from "../components/LayoutPicker.jsx";
import SenseMixer from "../components/SenseMixer.jsx";
import { formatChatMessage } from "../lib/formatMessage.js";
import { useSelection } from "../lib/selection.jsx";

function parse(s) { try { return s ? JSON.parse(s) : null; } catch { return null; } }

function ChatThread({ messages, thinking }) {
  const ref = useRef(null);
  useEffect(() => {
    const t = setTimeout(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, 50);
    return () => clearTimeout(t);
  }, [messages, thinking]);
  let lastSensiId = null;
  messages.forEach(m => { if (m.role === "s") lastSensiId = m.id; });
  return (
    <div className="thread" ref={ref}>
      <div className="thread-inner">
        {messages.map(m =>
          m.role === "s" ? (
            <div className="bubble-wrap" key={m.id}>
              {m.id === lastSensiId && !thinking ? <SensiAvatar size={28} /> : <div className="sensi-avatar-static" />}
              <div className="bubble-s"><div dangerouslySetInnerHTML={{ __html: formatChatMessage(m.text) }} /></div>
            </div>
          ) : (<div className="bubble-u" key={m.id}>{m.text}</div>)
        )}
        {thinking && <Thinking />}
      </div>
    </div>
  );
}

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

const DEFAULT_LAYERS = { fill: true, signatures: true, flow: false, topology: false };

export default function LayoutModeScreen({ messages, turns, thinking, persona, layoutId, onSend }) {
  const [chatOpen,     setChatOpen]     = useState(true);
  const [profileOpen,  setProfileOpen]  = useState(false);
  const [capOpen,      setCapOpen]      = useState(false);
  const [graphOpen,    setGraphOpen]    = useState(false);
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
    if (!activeTurn?.scores_json) return;
    try {
      const rs = JSON.parse(activeTurn.scores_json).rooms || [];
      if (rs.length) setActiveRoom(rs.reduce((a, b) => ((a.overallScore || 1) <= (b.overallScore || 1) ? a : b)).roomName);
    } catch { /* noop */ }
  }, [activeTurn?.id]); // eslint-disable-line

  const rooms         = parse(activeTurn?.scores_json)?.rooms || [];
  const avg           = rooms.length ? rooms.reduce((a, r) => a + (r.overallScore || 0), 0) / rooms.length : null;
  const conflictCount = parse(activeTurn?.conflicts_json)?.flaggedRooms?.length || 0;
  const ringClass     = avg == null ? "" : avg >= 0.65 ? "score-pass" : avg >= 0.45 ? "score-warn" : "score-fail";
  const initial       = persona?.name?.charAt(0).toUpperCase() || "";
  const metrics       = layers.topology ? activeTurn?.graph_data?.metrics : null;

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

  const toggleLayer = (k) => setLayers(l => ({ ...l, [k]: !l[k] }));

  return (
    <div className="layout-mode-screen">

      <div className="top-bar">
        <div className="top-bar-pill top-bar-pill--wide">
          <SensiAvatar size={26} />
          <span className="top-bar-label">sensi</span>
          <span className="top-bar-sep">|</span>
          <LayoutPicker layoutId={layoutId} onSelect={(id) => onSend(`load layout ${id}`)} onUpload={(id) => onSend(`analyse layout ${id}`)} />
          <div className="top-bar-status-group">
            {conflictCount > 0 && <span className="top-bar-conflict-badge">{conflictCount} {conflictCount === 1 ? "conflict" : "conflicts"}</span>}
            {avg != null && <span className={"top-bar-score-ring " + ringClass}>{avg.toFixed(2)}</span>}
            {persona && initial && (
              <button className="top-bar-user-avatar" onClick={() => setProfileOpen(true)} title="your comfort profile">{initial}</button>
            )}
          </div>
        </div>
      </div>

      <Capabilities open={capOpen} onClose={() => setCapOpen(false)} />

      <div className="lm-body">

        <AnimatePresence>
          {chatOpen && (
            <motion.div className="lm-chat-sidebar"
              initial={{ x: -40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: -40, opacity: 0 }}
              transition={{ duration: 0.2, ease: [0.22, 0.61, 0.36, 1] }}>
              <ChatThread messages={messages} thinking={thinking} />
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
            <LayerToggles layers={layers} onToggle={toggleLayer} />
            <button className={"layer-pill" + (graphOpen ? " active" : "")} onClick={() => setGraphOpen(true)} title="sense-coupling graph">sense graph ↗</button>
          </div>

          <div className="lm-viewer">
            <SensePlan rooms={rooms} layoutId={layoutId} layers={layers} graphData={activeTurn?.graph_data} />

            {/* topology metric pills */}
            {metrics && (
              <div className="metric-pills">
                {metrics.most_connected && metrics.most_connected !== "none" && <span className="metric-pill">hub · {metrics.most_connected}</span>}
                {metrics.bridge_rooms?.length > 0 && <span className="metric-pill">bridges · {metrics.bridge_rooms.join(", ")}</span>}
                {metrics.isolated_rooms?.length > 0 && <span className="metric-pill warn">isolated · {metrics.isolated_rooms.join(", ")}</span>}
              </div>
            )}

            {/* legend (corner) */}
            <div className="legend-corner"><Legend layers={layers} /></div>

            {/* focus card (right overlay, on room select) */}
            <AnimatePresence>
              {activeRoom && rooms.length > 0 && (
                <FocusCard key="focus-card" turn={activeTurn} persona={persona} onClose={() => setActiveRoom(null)} />
              )}
            </AnimatePresence>
          </div>

          <TimelineStrip turns={turns} activeTurnId={activeTurnId}
            onSelect={(id) => setActiveTurnId(id === activeTurnId ? null : id)} />
        </div>
      </div>

      {/* sense-coupling graph drawer */}
      <AnimatePresence>
        {graphOpen && (
          <>
            <motion.div className="graph-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setGraphOpen(false)} />
            <motion.div className="graph-drawer"
              initial={{ x: 380 }} animate={{ x: 0 }} exit={{ x: 380 }} transition={{ duration: 0.24, ease: [0.22, 0.61, 0.36, 1] }}>
              <div className="flex items-center justify-between">
                <span className="graph-drawer-title">sense coupling</span>
                <button className="fc-close" onClick={() => setGraphOpen(false)}>×</button>
              </div>
              <span className="graph-drawer-hint">node size = rooms failing · edges = couplings (solid research / dashed physics) · click to solo</span>
              <SenseGraph rooms={rooms} />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {spaceInput && <SpaceInput pos={spaceInput} onSend={send} onClose={() => setSpaceInput(null)} />}
      <ProfilePanel persona={persona} open={profileOpen} onClose={() => setProfileOpen(false)} onFullView={() => setProfileOpen(false)} />
    </div>
  );
}
