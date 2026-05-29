import { useState } from "react";
import SenseSpaceGraph from "./SenseSpaceGraph.jsx";
import { scoreColor } from "../lib/constants.js";

const ACTION_ICONS = {
  analyze:         "◎",
  detect:          "!",
  full:            "▦",
  change_material: "◈",
  modify_glazing:  "◇",
  add_furniture:   "✿",
  topologic:       "⬡",
  biophilic:       "❧",
  compare:         "⇌",
  follow_up:       "↩",
  overview:        "≡",
  chitchat:        "○",
};

function MiniRing({ score, conflicts }) {
  if (score == null) return null;
  const color = scoreColor(score);
  return (
    <span className="tl-mini-ring" style={{ borderColor: color, color }}>
      {score.toFixed(2)}
      {conflicts > 0 && <span className="tl-conflict-dot">{conflicts}</span>}
    </span>
  );
}

function TurnChip({ turn, active, onSelect, onExpand, expanded }) {
  const icon = ACTION_ICONS[turn.action] || "○";
  return (
    <div
      className={"tl-chip" + (active ? " active" : "") + (expanded ? " expanded" : "")}
      onClick={() => onSelect(turn.id)}
    >
      <span className="tl-chip-icon">{icon}</span>
      <span className="tl-chip-label">{turn.label}</span>
      <MiniRing score={turn.avgScore} conflicts={turn.conflictCount} />
      {(turn.scores_json || turn.graph_data?.nodes?.length) && (
        <button
          className="tl-expand-btn"
          title={expanded ? "collapse" : "expand graph"}
          onClick={(e) => { e.stopPropagation(); onExpand(expanded ? null : turn.id); }}
        >
          {expanded ? "▲" : "▼"}
        </button>
      )}
    </div>
  );
}

export default function TimelineStrip({ turns, activeTurnId, onSelect }) {
  const [expandedId, setExpandedId] = useState(null);
  if (!turns || !turns.length) return null;

  const expandedTurn = expandedId ? turns.find((t) => t.id === expandedId) : null;

  return (
    <div className="timeline-strip">
      <div className="tl-chips-row">
        <span className="tl-label">timeline</span>
        {turns.map((turn) => (
          <TurnChip
            key={turn.id}
            turn={turn}
            active={turn.id === activeTurnId}
            expanded={turn.id === expandedId}
            onSelect={onSelect}
            onExpand={setExpandedId}
          />
        ))}
      </div>

      {expandedTurn && (
        <div className="tl-graph-expand">
          <SenseSpaceGraph
            graphData={expandedTurn.graph_data}
            scoresJson={expandedTurn.scores_json}
            conflictsJson={expandedTurn.conflicts_json}
          />
        </div>
      )}
    </div>
  );
}
