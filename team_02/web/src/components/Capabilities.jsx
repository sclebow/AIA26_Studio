import { useState } from "react";
import { SC, SI } from "../lib/constants.js";

// Capabilities modal — ported from the static cap-overlay markup in index.html.
// Only the per-sense capability pills + short label live here; the glyph and hue
// come from the sense registry (lib/senses.js) so there's no second color copy.
const SENSE_CAPS = {
  acoustic:  { abbr: "aco", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["crefine", "⊙ topology"], ["crefine", "⊡ furniture"], ["soon", "◨ material"]] },
  thermal:   { abbr: "thm", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["crefine", "⊙ topology"], ["soon", "◨ material"], ["soon", "⊟ glazing"]] },
  visual:    { abbr: "vis", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["slive", "◎ inspire"], ["crefine", "⊡ furniture"], ["soon", "◨ material"], ["soon", "⊟ glazing"]] },
  spatial:   { abbr: "spt", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["slive", "⊞ areas"], ["slive", "≡ overview"], ["crefine", "⊙ topology"], ["crefine", "⊡ furniture"], ["road", "⇄ compare versions"], ["road", "⇅ compare personas"], ["road", "⊗ multiagent"]] },
  olfactory: { abbr: "olf", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["crefine", "⊡ furniture"], ["soon", "◨ material"], ["road", "∾ biophilic audit"]] },
  tactile:   { abbr: "tac", pills: [["slive", "◈ score"], ["slive", "× conflicts"], ["slive", "▷ suggest"], ["crefine", "⊡ furniture"], ["soon", "◨ material"]] },
};
const SENSE_ROWS = Object.entries(SENSE_CAPS).map(([key, c]) => ({
  key, sym: SI[key], name: c.abbr, sc: SC[key], pills: c.pills,
}));
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
