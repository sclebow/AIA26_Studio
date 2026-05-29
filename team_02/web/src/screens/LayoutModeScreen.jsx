import { useCallback, useEffect, useRef, useState } from "react";
import SensiAvatar from "../components/SensiAvatar.jsx";
import Thinking from "../components/Thinking.jsx";
import AnalysisPanel from "./AnalysisPanel.jsx";
import ProfilePanel from "../components/ProfilePanel.jsx";
import Capabilities from "../components/Capabilities.jsx";
import LayoutPlan from "../components/LayoutPlan.jsx";
import SenseSpaceGraph from "../components/SenseSpaceGraph.jsx";
import TimelineStrip from "../components/TimelineStrip.jsx";
import LayoutPicker from "../components/LayoutPicker.jsx";
import { formatChatMessage } from "../lib/formatMessage.js";

function parse(s) { try { return s ? JSON.parse(s) : null; } catch { return null; } }

// ── Chips linking chat bubble → analysis panel ────────────────────────────────
function Chips({ depth, openPanel }) {
  const chips = [["scores","scores"]];
  if (depth === "detect" || depth === "full") chips.push(["conflicts","conflicts"]);
  if (depth === "full") { chips.push(["suggestions","suggestions"]); chips.push(["score-interp","analysis"]); }
  return (
    <div className="ap-chips-row">
      {chips.map(([sec, label]) => (
        <button className="ap-jump-chip" key={sec}
          onClick={() => {
            openPanel();
            setTimeout(() => document.getElementById("ap-"+sec)?.scrollIntoView({ behavior:"smooth", block:"start" }), 280);
          }}>
          <span className="ap-chip-arrow">↗</span>{label}
        </button>
      ))}
    </div>
  );
}

// ── Chat thread (sidebar mode) ────────────────────────────────────────────────
function ChatThread({ messages, thinking, openPanel }) {
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
              {m.id === lastSensiId && !thinking
                ? <SensiAvatar size={28} />
                : <div className="sensi-avatar-static" />}
              <div className="bubble-s">
                <div dangerouslySetInnerHTML={{ __html: formatChatMessage(m.text) }} />
                {m.data?.scores_json && <Chips depth={m.data.analysis_depth || "analyze"} openPanel={openPanel} />}
              </div>
            </div>
          ) : (
            <div className="bubble-u" key={m.id}>{m.text}</div>
          )
        )}
        {thinking && <Thinking />}
      </div>
    </div>
  );
}

// ── Space-bar floating input ──────────────────────────────────────────────────
function SpaceInput({ pos, onSend, onClose }) {
  const [val, setVal] = useState("");
  const inputRef = useRef(null);
  useEffect(() => { inputRef.current?.focus(); }, []);

  const submit = () => {
    const t = val.trim();
    if (!t) { onClose(); return; }
    onSend(t);
    onClose();
  };

  return (
    <div
      className="space-input-wrap"
      style={{ left: pos.x, top: pos.y }}
      onMouseDown={e => e.stopPropagation()}
    >
      <textarea
        ref={inputRef}
        className="space-input-ta"
        placeholder="ask sensi…"
        value={val}
        rows={1}
        onChange={e => setVal(e.target.value)}
        onKeyDown={e => {
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
          if (e.key === "Escape") onClose();
        }}
      />
      <button className="space-input-send" onClick={submit}>→</button>
    </div>
  );
}

// ── Main screen ───────────────────────────────────────────────────────────────
export default function LayoutModeScreen({ messages, turns, thinking, persona, layoutId, onSend }) {
  const [immersed,     setImmersed]     = useState(false);
  const [centerMode,   setCenterMode]   = useState("comfort"); // "comfort" | "sense-space"
  const [panelOpen,    setPanelOpen]    = useState(false);
  const [profileOpen,  setProfileOpen]  = useState(false);
  const [capOpen,      setCapOpen]      = useState(false);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [activeTurnId, setActiveTurnId] = useState(null);
  const [spaceInput,   setSpaceInput]   = useState(null); // {x, y} | null
  const [draft,        setDraft]        = useState("");
  const taRef    = useRef(null);
  const centerRef = useRef(null);

  // Latest turn with analysis data (default), or the chip-selected turn
  const latestTurn = turns.length ? turns[turns.length - 1] : null;
  const activeTurn = activeTurnId ? turns.find(t => t.id === activeTurnId) : latestTurn;

  // Auto-open panel when first analysis arrives
  useEffect(() => {
    if (latestTurn?.scores_json) { setPanelOpen(true); setActiveTurnId(null); }
  }, [latestTurn?.id]); // eslint-disable-line

  // Auto-select worst room when turn changes
  useEffect(() => {
    if (!activeTurn?.scores_json) return;
    try {
      const rooms = JSON.parse(activeTurn.scores_json).rooms || [];
      if (rooms.length) {
        const worst = rooms.reduce((a,b) => (a.overallScore||1) <= (b.overallScore||1) ? a : b);
        setSelectedRoom(worst.roomName);
      }
    } catch {}
  }, [activeTurn?.id]); // eslint-disable-line

  // Scoreboard values for top bar
  const rooms         = parse(activeTurn?.scores_json)?.rooms || [];
  const avg           = rooms.length ? rooms.reduce((a,r) => a+(r.overallScore||0), 0) / rooms.length : null;
  const conflictCount = parse(activeTurn?.conflicts_json)?.flaggedRooms?.length || 0;
  const ringClass     = avg == null ? "" : avg >= 0.65 ? "score-pass" : avg >= 0.45 ? "score-warn" : "score-fail";
  const initial       = persona?.name?.charAt(0).toUpperCase() || "";

  // Space-bar handler: summon input at cursor, only in immersed mode
  const cursorPos = useRef({ x: 200, y: 200 });
  useEffect(() => {
    const onMove = e => { cursorPos.current = { x: e.clientX, y: e.clientY }; };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  useEffect(() => {
    const onKey = e => {
      // Only trigger in immersed mode; not when already typing in a field
      if (!immersed) return;
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
      if (e.code === "Space") {
        e.preventDefault();
        setSpaceInput({ x: cursorPos.current.x - 140, y: cursorPos.current.y - 24 });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [immersed]);

  // Dismiss space input on outside click
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

  const handleLayoutSelect = (id) => {
    onSend(`load layout ${id}`);
  };
  const handleLayoutUpload = (id, name) => {
    onSend(`analyse layout ${id}`);
  };

  return (
    <div className={"layout-mode-screen" + (immersed ? " immersed" : "")}>

      {/* ── TOP BAR ── */}
      <div className="top-bar">
        <div className="top-bar-pill top-bar-pill--wide">
          <SensiAvatar size={26} />
          <span className="top-bar-label">sensi</span>
          <span className="top-bar-sep">|</span>

          {/* Layout picker */}
          <LayoutPicker
            layoutId={layoutId}
            onSelect={handleLayoutSelect}
            onUpload={handleLayoutUpload}
          />

          <div className="top-bar-status-group">
            {conflictCount > 0 && (
              <span className="top-bar-conflict-badge"
                onClick={() => { setPanelOpen(true); setTimeout(() => document.getElementById("ap-conflicts")?.scrollIntoView({behavior:"smooth"}), 280); }}>
                {conflictCount} {conflictCount === 1 ? "conflict" : "conflicts"}
              </span>
            )}
            {avg != null && (
              <span className={"top-bar-score-ring " + ringClass}>{avg.toFixed(2)}</span>
            )}
            {persona && initial && (
              <button className="top-bar-user-avatar" onClick={() => setProfileOpen(true)} title="your comfort profile">
                {initial}
              </button>
            )}
          </div>
        </div>
      </div>

      <Capabilities open={capOpen} onClose={() => setCapOpen(false)} />

      {/* ── BODY: 3 zones ── */}
      <div className="lm-body">

        {/* ZONE 1: Chat sidebar (hidden when immersed) */}
        {!immersed && (
          <div className="lm-chat-sidebar">
            <ChatThread messages={messages} thinking={thinking} openPanel={() => setPanelOpen(true)} />
            <div className="lm-input-area">
              <button className={"cap-btn" + (capOpen ? " on" : "")} onClick={() => setCapOpen(o => !o)} title="capabilities">⊞</button>
              <div className="send-row" style={{ flex:1 }}>
                <textarea
                  ref={taRef}
                  className="sensi-input"
                  placeholder="ask sensi about your layout…"
                  value={draft}
                  onChange={e => {
                    setDraft(e.target.value);
                    e.target.style.height = "50px";
                    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
                  }}
                  onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                />
                <button className="btn-send" onClick={() => send()}>→</button>
              </div>
            </div>
          </div>
        )}

        {/* ZONE 2: Layout center */}
        <div className="lm-center" ref={centerRef}>

          {/* Center controls */}
          <div className="lm-center-controls">
            <div className="lm-mode-toggle">
              <button className={"lm-mode-btn" + (centerMode === "comfort"     ? " active" : "")} onClick={() => setCenterMode("comfort")}>comfort</button>
              <button className={"lm-mode-btn" + (centerMode === "sense-space" ? " active" : "")} onClick={() => setCenterMode("sense-space")}>sense-space</button>
            </div>
            <button
              className={"lm-immerse-btn" + (immersed ? " active" : "")}
              title={immersed ? "show chat (or press Space to type)" : "immersive mode"}
              onClick={() => setImmersed(o => !o)}
            >
              {immersed ? "⛶" : "⛶"}
            </button>
            {immersed && (
              <span className="lm-space-hint">space to type</span>
            )}
          </div>

          {/* Viewer */}
          <div className="lm-viewer">
            {centerMode === "comfort" ? (
              <LayoutPlan
                rooms={rooms}
                selectedRoom={selectedRoom}
                onSelect={setSelectedRoom}
                layoutId={layoutId}
                layoutDiff={activeTurn?.layout_diff}
                biophilicData={activeTurn?.biophilic_data}
                showMode="comfort"
              />
            ) : (
              <SenseSpaceGraph
                graphData={activeTurn?.graph_data}
                scoresJson={activeTurn?.scores_json}
                conflictsJson={activeTurn?.conflicts_json}
                onSelect={setSelectedRoom}
                selectedId={selectedRoom}
              />
            )}
          </div>

          {/* Timeline strip */}
          <TimelineStrip
            turns={turns}
            activeTurnId={activeTurnId}
            onSelect={(id) => { setActiveTurnId(id === activeTurnId ? null : id); setPanelOpen(true); }}
          />
        </div>

        {/* ZONE 3: Analysis panel */}
        <AnalysisPanel
          data={activeTurn}
          open={panelOpen}
          onClose={() => setPanelOpen(false)}
          layoutId={layoutId}
          selectedRoom={selectedRoom}
          onSelectRoom={setSelectedRoom}
        />
      </div>

      {/* Space-bar floating input (immersed mode) */}
      {spaceInput && (
        <SpaceInput
          pos={spaceInput}
          onSend={send}
          onClose={() => setSpaceInput(null)}
        />
      )}

      <ProfilePanel persona={persona} open={profileOpen} onClose={() => setProfileOpen(false)} onFullView={() => setProfileOpen(false)} />
    </div>
  );
}
