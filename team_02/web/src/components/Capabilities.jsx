import { useState } from "react";
import { SC, SI } from "../lib/constants.js";

// Capabilities menu. ONE registry of what Sensi can do; two projections:
//   · by action — verb families (analyze / shape / explore / …)
//   · by sense  — what shapes & reveals each sense: the levers + lenses for each one.
//
// Each capability carries two ORTHOGONAL signals:
//   · type — agentic (◆ changes the layout) / analytic (◇ reveals + measures) /
//            general (· talk + session). Encoded by a leading mark + pill shape.
//   · tier — live / refining / soon. Encoded by a small trailing status dot.
// …and a `launch` phrase: clicking a chip drops it into the chat (the menu is also a
// launcher). A phrase ending in "the " expects a room to finish the sentence.
//
// Keep in sync with the backend it mirrors: agentic = edit ops in
// nodes/editing/edit_planner.ALLOWED_OPS; analytic/general = nodes/routing/action_classifier.
const TIER_DOT = { refining: "rgba(80,195,210,.85)", soon: "rgba(212,185,106,.85)" };
const TYPE_GLYPH = { agentic: "◆", analytic: "◇", general: "·" }; // ◆ ◇ ·
const ABBR = { thermal: "thm", visual: "vis", acoustic: "aco", spatial: "spt", olfactory: "olf", tactile: "tac" };

const CAP = {
  // analyze (analytic)
  score:      { label: "score",       type: "analytic", tier: "live", launch: "analyze this layout" },
  conflicts:  { label: "conflicts",   type: "analytic", tier: "live", launch: "what comfort conflicts does this layout have?" },
  suggest:    { label: "suggest",     type: "analytic", tier: "live", launch: "suggest improvements" },
  // shape (agentic) — the edit vocabulary
  addWindow:  { label: "add window",  type: "agentic", tier: "live", launch: "add a window to the " },
  moveWindow: { label: "move window", type: "agentic", tier: "live", launch: "move the window to the south wall of the " },
  glazing:    { label: "glazing",     type: "agentic", tier: "live", launch: "upgrade the glazing in the " },
  ventilation:{ label: "ventilation", type: "agentic", tier: "live", launch: "improve the ventilation in the " },
  floorMat:   { label: "flooring",    type: "agentic", tier: "live", launch: "change the floor to wood in the " },
  wallMat:    { label: "wall finish", type: "agentic", tier: "live", launch: "change the walls to cork in the " },
  plant:      { label: "plant",       type: "agentic", tier: "live", launch: "add a plant to the " },
  curtains:   { label: "curtains",    type: "agentic", tier: "live", launch: "add curtains to the " },
  furniture:  { label: "furniture",   type: "agentic", tier: "live", launch: "add a sofa to the " },
  remove:     { label: "remove",      type: "agentic", tier: "live", launch: "remove the " },
  // preview / explore / compare (analytic)
  preview:    { label: "what-if",     type: "analytic", tier: "live", launch: "what if I " },
  overview:   { label: "overview",    type: "analytic", tier: "live", launch: "give me an overview of the rooms" },
  areas:      { label: "areas",       type: "analytic", tier: "live", launch: "what are the room areas?" },
  topology:   { label: "topology",    type: "analytic", tier: "live", launch: "analyze the room connectivity" },
  galaxy:     { label: "galaxy",      type: "analytic", tier: "live", launch: "" },   // opened from the galaxy ↗ button
  biophilic:  { label: "biophilic",   type: "analytic", tier: "refining", launch: "talk green to me" },
  cmpVersions:{ label: "versions",    type: "analytic", tier: "live", launch: "" },   // automatic after every edit
  cmpPersonas:{ label: "personas",    type: "analytic", tier: "refining", launch: "compare this layout for two personas" },
  // converse / session (general)
  inspire:    { label: "inspire",     type: "general", tier: "live", launch: "inspire me" },
  persona:    { label: "persona",     type: "general", tier: "live", launch: "show my comfort profile" },
  followup:   { label: "follow-up",   type: "general", tier: "live", launch: "" },
  chitchat:   { label: "chitchat",    type: "general", tier: "live", launch: "" },
  checkpoint: { label: "checkpoints", type: "general", tier: "live", launch: "" },   // committed from the chat bar
  ecosystem:  { label: "multi-agent", type: "general", tier: "soon", launch: "" },
};

// BY ACTION — verb families (what you can ask).
const FAMILIES = [
  { title: "analyze",  ids: ["score", "conflicts", "suggest"] },
  { title: "shape",    ids: ["addWindow", "moveWindow", "glazing", "ventilation", "floorMat", "wallMat", "plant", "curtains", "furniture", "remove"] },
  { title: "preview",  ids: ["preview"] },
  { title: "explore",  ids: ["overview", "areas", "topology", "galaxy", "biophilic"] },
  { title: "compare",  ids: ["cmpVersions", "cmpPersonas"] },
  { title: "converse", ids: ["inspire", "persona", "followup", "chitchat"] },
  { title: "session",  ids: ["checkpoint", "ecosystem"] },
];

// BY SENSE — what shapes (◆) & reveals (◇) each sense. Mirrors compute_comfort_scores:
// spatial is volume-driven (no agentic lever), so it offers the analytic lenses instead.
const SENSE_LEVERS = {
  thermal:   ["glazing", "addWindow", "moveWindow", "ventilation"],
  visual:    ["addWindow", "glazing", "plant"],
  acoustic:  ["curtains", "wallMat", "floorMat"],
  spatial:   ["topology", "galaxy", "areas"],
  olfactory: ["ventilation", "plant", "biophilic"],
  tactile:   ["floorMat", "wallMat", "furniture"],
};

function Chip({ id, onLaunch }) {
  const c = CAP[id];
  if (!c) return null;
  const launchable = !!(c.launch && onLaunch);
  return (
    <button
      className={"cpill type-" + c.type + " tier-" + c.tier + (launchable ? " is-launch" : "")}
      title={launchable ? `try: ${c.launch.trim()}…` : (c.tier === "soon" ? "coming soon" : c.label)}
      onClick={launchable ? () => onLaunch(c.launch) : undefined}>
      <span className="cpill-type" aria-hidden="true">{TYPE_GLYPH[c.type]}</span>
      {c.label}
      {c.tier !== "live" && <span className="cpill-dot" style={{ background: TIER_DOT[c.tier] }} />}
    </button>
  );
}

export default function Capabilities({ open, onClose, onLaunch }) {
  const [view, setView] = useState("action");
  if (!open) return null;
  return (
    <div className="cap-overlay open" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="cap-panel">
        <div className="cap-hdr">
          <span className="cap-title">capabilities</span>
          <div className="cap-vtoggle">
            <button className={"cap-vt" + (view === "action" ? " on" : "")} onClick={() => setView("action")}>by action</button>
            <button className={"cap-vt" + (view === "sense" ? " on" : "")} onClick={() => setView("sense")}>by sense</button>
          </div>
          <button className="cap-close" onClick={onClose}>×</button>
        </div>

        <div className="cap-hint">tap a capability to drop it into the chat</div>

        <div className="cap-body">
          {view === "action" ? (
            <div className="cview on">
              {FAMILIES.map((f) => (
                <div className="arow" key={f.title}>
                  <div className="arow-title">{f.title}</div>
                  <div className="arow-pills">
                    {f.ids.map((id) => <Chip key={id} id={id} onLaunch={onLaunch} />)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="cview on">
              <div className="cap-sub">what shapes &amp; reveals each sense</div>
              {Object.entries(SENSE_LEVERS).map(([sense, ids]) => (
                <div className="srow" key={sense} style={{ "--sc": SC[sense] }}>
                  <div className="srow-label">
                    <span className="srow-sym">{SI[sense]}</span>
                    <span className="srow-name">{ABBR[sense]}</span>
                  </div>
                  <div className="srow-pills">
                    {ids.length
                      ? ids.map((id) => <Chip key={id} id={id} onLaunch={onLaunch} />)
                      : <span className="srow-note">shaped by room volume — fixed here</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="cap-legend">
          <span className="leg-item"><span className="leg-mk">{TYPE_GLYPH.agentic}</span>shape</span>
          <span className="leg-item"><span className="leg-mk">{TYPE_GLYPH.analytic}</span>study</span>
          <span className="leg-item"><span className="leg-mk">{TYPE_GLYPH.general}</span>talk</span>
          <span className="leg-sep" />
          <span className="leg-item"><span className="leg-dot" style={{ background: TIER_DOT.refining }} />refining</span>
          <span className="leg-item"><span className="leg-dot" style={{ background: TIER_DOT.soon }} />soon</span>
        </div>
      </div>
    </div>
  );
}
