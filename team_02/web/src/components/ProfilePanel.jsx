import { SC, SI, SENSES, BASELINES, IMPLICATIONS } from "../lib/constants.js";

// Slide-in comfort-profile panel in the chat screen (mirrors _renderPanelContent).
export default function ProfilePanel({ persona, open, onClose, onFullView }) {
  const p = persona || {};
  const weights = p.comfort_weights || {};
  const priorities = p.sensory_priorities || SENSES;
  const role = (p.role || "client").toLowerCase();

  return (
    <div className={"profile-panel" + (open ? " open" : "")}>
      <div className="panel-header">
        <svg width="16" height="16" viewBox="0 0 32 32" fill="none" style={{ opacity: 0.5 }}>
          <circle cx="16" cy="16" r="14.5" stroke="#E8836A" strokeWidth=".8" />
          <circle cx="16" cy="16" r="9.5" stroke="#9B8FD4" strokeWidth=".8" />
          <circle cx="16" cy="16" r="4.5" stroke="#8BB88A" strokeWidth=".8" />
          <circle cx="16" cy="16" r="1.4" fill="#F0EDE8" opacity=".80" />
        </svg>
        <span className="top-bar-label">comfort profile</span>
        <button className="btn-panel-full" onClick={onFullView}>full view</button>
        <button className="panel-close" onClick={onClose}>×</button>
      </div>
      <div className="panel-scroll">
        <div>
          <div className="persona-section-label" style={{ marginTop: 0 }}>top priorities</div>
          {priorities.slice(0, 3).map((s) => (
            <div key={s} style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 10 }}>
              <span style={{ color: SC[s], fontSize: 13, flexShrink: 0, marginTop: 1 }}>{SI[s]}</span>
              <div>
                <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 7, letterSpacing: ".16em", textTransform: "uppercase", color: SC[s], marginBottom: 3 }}>{s}</div>
                <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontWeight: 300, fontSize: 10, lineHeight: 1.5, color: "rgba(240,237,232,.42)" }}>{(IMPLICATIONS[s] && IMPLICATIONS[s][role]) || ""}</div>
              </div>
            </div>
          ))}
        </div>
        <div>
          <div className="persona-section-label">sense spectrum</div>
          {SENSES.map((s) => {
            const w = weights[s] != null ? weights[s] : 0;
            const wPct = Math.min(100, Math.max(0, w * 100));
            const bPct = Math.min(100, Math.max(0, (BASELINES[s] || 0.5) * 100));
            return (
              <div className="pbar-row" key={s} style={{ marginBottom: 8 }}>
                <span className="pbar-lbl" style={{ color: SC[s] }}>{SI[s]} {s}</span>
                <div className="pbar-track">
                  <div className="pbar-fill" style={{ width: `${wPct}%`, background: SC[s], opacity: 0.6 }} />
                  <div className="pbar-tick" style={{ left: `${bPct}%` }} />
                </div>
                <span className="pbar-val">{w.toFixed ? w.toFixed(1) : w}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
