import { useState } from "react";

// Capabilities modal — ported from the static cap-overlay markup in index.html.
const SENSE_ROWS = [
  { sym: "∿", name: "aco", sc: "#9B8FD4", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["crefine", "⊙ topology"], ["crefine", "⊡ furniture"], ["soon", "◨ material"]] },
  { sym: "△", name: "thm", sc: "#E8836A", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["crefine", "⊙ topology"], ["soon", "◨ material"], ["soon", "⊟ glazing"]] },
  { sym: "○", name: "vis", sc: "#D4B96A", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["slive", "◎ inspire"], ["crefine", "⊡ furniture"], ["soon", "◨ material"], ["soon", "⊟ glazing"]] },
  { sym: "□", name: "spt", sc: "#6AB8C8", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["slive", "⊞ areas"], ["slive", "≡ overview"], ["crefine", "⊙ topology"], ["crefine", "⊡ furniture"], ["road", "⇄ compare versions"], ["road", "⇅ compare personas"], ["road", "⊗ multiagent"]] },
  { sym: "≈", name: "olf", sc: "#8BB88A", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["crefine", "⊡ furniture"], ["soon", "◨ material"], ["road", "∾ biophilic audit"]] },
  { sym: "∶", name: "tac", sc: "#C4A882", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["crefine", "⊡ furniture"], ["soon", "◨ material"]] },
];
const ACTION_ROWS = [
  { title: "◈  analyze", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"]] },
  { title: "⊠  modify", pills: [["crefine", "⊡ furniture"], ["soon", "◨ material"], ["soon", "⊟ glazing"]] },
  { title: "⊞  explore", pills: [["slive", "⊞ areas"], ["slive", "≡ overview"], ["crefine", "⊙ topology"]] },
  { title: "⊙  converse", pills: [["slive", "◎ inspire"], ["slive", "∷ persona"], ["slive", "↩ follow-up"], ["slive", "◌ chitchat"]] },
  { title: "⇄  compare", pills: [["road", "⇄ versions"], ["road", "⇅ personas"]] },
  { title: "∾  biophilic", pills: [["road", "∾ biophilic audit"]] },
  { title: "⊗  ecosystem", pills: [["road", "⊗ multiagent"]] },
];

export default function Capabilities({ open, onClose }) {
  const [view, setView] = useState("sense");
  if (!open) return null;
  return (
    <div className="cap-overlay open" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="cap-panel">
        <div className="cap-hdr">
          <span className="cap-title">capabilities</span>
          <div className="cap-vtoggle">
            <button className={"cap-vt" + (view === "sense" ? " on" : "")} onClick={() => setView("sense")}>by sense</button>
            <button className={"cap-vt" + (view === "action" ? " on" : "")} onClick={() => setView("action")}>by action</button>
          </div>
          <button className="cap-close" onClick={onClose}>×</button>
        </div>
        <div className="cap-body">
          {view === "sense" && (
            <div className="cview on">
              {SENSE_ROWS.map((row) => (
                <div className="srow" key={row.name} style={{ "--sc": row.sc }}>
                  <div className="srow-label"><span className="srow-sym">{row.sym}</span><span className="srow-name">{row.name}</span></div>
                  <div className="srow-pills">
                    {row.pills.map(([cls, label], i) => <span className={"cpill " + cls} key={i}>{label}</span>)}
                  </div>
                </div>
              ))}
            </div>
          )}
          {view === "action" && (
            <div className="cview on">
              {ACTION_ROWS.map((row) => (
                <div className="arow" key={row.title}>
                  <div className="arow-title">{row.title}</div>
                  <div className="arow-pills">
                    {row.pills.map(([cls, label], i) => <span className={"cpill " + cls} key={i}>{label}</span>)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="cap-legend">
          <span className="leg-item"><span className="leg-dot" style={{ background: "rgba(100,200,120,.85)" }} />live now</span>
          <span className="leg-item"><span className="leg-dot" style={{ background: "rgba(80,195,210,.85)" }} />refining</span>
          <span className="leg-item"><span className="leg-dot" style={{ background: "rgba(212,185,106,.85)" }} />coming soon</span>
          <span className="leg-item"><span className="leg-dot" style={{ background: "rgba(210,85,85,.85)" }} />bonus</span>
        </div>
      </div>
    </div>
  );
}
