import { SC, SI, SENSES, BASELINES, IMPLICATIONS } from "../lib/constants.js";
import SenseBar from "../viz/SenseBar.jsx";

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
          <circle cx="16" cy="16" r="14.5" stroke={SC.thermal} strokeWidth=".8" />
          <circle cx="16" cy="16" r="9.5" stroke={SC.acoustic} strokeWidth=".8" />
          <circle cx="16" cy="16" r="4.5" stroke={SC.olfactory} strokeWidth=".8" />
          <circle cx="16" cy="16" r="1.4" fill="var(--fg)" opacity=".80" />
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
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: ".16em", textTransform: "uppercase", color: SC[s], marginBottom: 3 }}>{s}</div>
                <div style={{ fontFamily: "var(--font-sans)", fontWeight: 300, fontSize: 11, lineHeight: 1.5, color: "rgba(240,237,232,.42)" }}>{(IMPLICATIONS[s] && IMPLICATIONS[s][role]) || ""}</div>
              </div>
            </div>
          ))}
        </div>
        <div>
          <div className="persona-section-label">sense spectrum</div>
          {SENSES.map((s) => {
            const w = weights[s] != null ? weights[s] : 0;
            return <SenseBar key={s} sense={s} value={w} baseline={BASELINES[s] || 0.5} style={{ marginBottom: 8 }} />;
          })}
        </div>
      </div>
    </div>
  );
}
