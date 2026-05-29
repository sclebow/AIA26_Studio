import { useEffect, useRef, useState } from "react";
import SensiAvatar from "../components/SensiAvatar.jsx";
import Thinking from "../components/Thinking.jsx";
import AnalysisPanel from "./AnalysisPanel.jsx";
import ProfilePanel from "../components/ProfilePanel.jsx";
import Capabilities from "../components/Capabilities.jsx";
import { formatChatMessage } from "../lib/formatMessage.js";

function parse(s) { try { return s ? JSON.parse(s) : null; } catch { return null; } }

function jumpPanel(section, openPanel) {
  openPanel();
  setTimeout(() => {
    const el = document.getElementById("ap-" + section);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 280);
}

function Chips({ depth, openPanel }) {
  const chips = [["scores", "scores"]];
  if (depth === "detect" || depth === "full") chips.push(["conflicts", "conflicts"]);
  if (depth === "full") { chips.push(["suggestions", "suggestions"]); chips.push(["score-interp", "analysis"]); }
  return (
    <div className="ap-chips-row">
      {chips.map(([sec, label]) => (
        <button className="ap-jump-chip" key={sec} onClick={() => jumpPanel(sec, openPanel)}>
          <span className="ap-chip-arrow">↗</span>{label}
        </button>
      ))}
    </div>
  );
}

function ChatThread({ messages, thinking, openPanel }) {
  const ref = useRef(null);
  useEffect(() => {
    const t = setTimeout(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, 50);
    return () => clearTimeout(t);
  }, [messages, thinking]);

  let lastSensiId = null;
  messages.forEach((m) => { if (m.role === "s") lastSensiId = m.id; });

  return (
    <div className="thread" ref={ref}>
      <div className="thread-inner">
        {messages.map((m) =>
          m.role === "s" ? (
            <div className="bubble-wrap" key={m.id}>
              {m.id === lastSensiId && !thinking ? <SensiAvatar size={28} /> : <div className="sensi-avatar-static" />}
              <div className="bubble-s" style={{ marginBottom: 0 }}>
                <div dangerouslySetInnerHTML={{ __html: formatChatMessage(m.text) }} />
                {m.data && m.data.scores_json && <Chips depth={m.data.analysis_depth || "analyze"} openPanel={openPanel} />}
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

export default function ChatScreen({ messages, thinking, persona, layoutId, onSend }) {
  const [draft, setDraft] = useState("");
  const taRef = useRef(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [capOpen, setCapOpen] = useState(false);

  let latestData = null;
  messages.forEach((m) => { if (m.data && m.data.scores_json) latestData = m.data; });
  useEffect(() => { if (latestData) setPanelOpen(true); }, [latestData]);

  const sc = parse(latestData && latestData.scores_json);
  const cf = parse(latestData && latestData.conflicts_json);
  const roomsArr = (sc && sc.rooms) || [];
  const avg = roomsArr.length ? roomsArr.reduce((a, r) => a + (r.overallScore || 0), 0) / roomsArr.length : null;
  const conflictCount = (cf && cf.flaggedRooms) ? cf.flaggedRooms.length : 0;
  const ringClass = avg == null ? "" : avg >= 0.65 ? "score-pass" : avg >= 0.45 ? "score-warn" : "score-fail";

  const send = () => {
    const t = draft.trim();
    if (!t) return;
    setDraft("");
    if (taRef.current) taRef.current.style.height = "50px";
    onSend(t);
  };

  const initial = persona && persona.name ? persona.name.charAt(0).toUpperCase() : "";

  return (
    <div className="screen active">
      <div className="top-bar">
        <div className="top-bar-pill top-bar-pill--wide">
          <SensiAvatar size={26} className="" />
          <span className="top-bar-label">sensi</span>
          <span className="top-bar-sep">|</span>
          <span className="top-bar-section">layout</span>
          {layoutId && (
            <div className="top-bar-layout-badge" style={{ display: "flex" }}>
              <div className="top-bar-layout-dot" />
              <span className="top-bar-layout-id">{String(layoutId).replace(/^layout[- ]?/i, "")}</span>
            </div>
          )}
          <div className="top-bar-status-group" style={{ display: "flex" }}>
            {conflictCount > 0 && (
              <span className="top-bar-conflict-badge" onClick={() => jumpPanel("conflicts", () => setPanelOpen(true))}>
                {conflictCount} {conflictCount === 1 ? "conflict" : "conflicts"}
              </span>
            )}
            {avg != null && <span className={"top-bar-score-ring " + ringClass} style={{ display: "flex" }}>{avg.toFixed(2)}</span>}
            {persona && initial && (
              <button className="top-bar-user-avatar" style={{ display: "flex" }} onClick={() => setProfileOpen(true)} title="your comfort profile">{initial}</button>
            )}
          </div>
        </div>
      </div>

      <Capabilities open={capOpen} onClose={() => setCapOpen(false)} />

      <div id="chat-body">
        <div id="chat-left" className={panelOpen ? "panel-open" : ""}>
          <ChatThread messages={messages} thinking={thinking} openPanel={() => setPanelOpen(true)} />
          <div className="input-area" style={{ maxWidth: 560, margin: "0 auto", width: "100%" }}>
            <div style={{ display: "flex", alignItems: "center" }}>
              <button className={"cap-btn" + (capOpen ? " on" : "")} onClick={() => setCapOpen((o) => !o)} title="capabilities">⊞</button>
              <div className="send-row" style={{ flex: 1 }}>
                <textarea
                  ref={taRef}
                  className="sensi-input"
                  placeholder="ask sensi about your layout…"
                  value={draft}
                  onChange={(e) => {
                    setDraft(e.target.value);
                    e.target.style.height = "50px";
                    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
                  }}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                />
                <button className="btn-send" onClick={send}>→</button>
              </div>
            </div>
          </div>
        </div>

        <AnalysisPanel data={latestData} open={panelOpen} onClose={() => setPanelOpen(false)} layoutId={layoutId} />
      </div>

      <ProfilePanel
        persona={persona}
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
        onFullView={() => { setProfileOpen(false); }}
      />
    </div>
  );
}
