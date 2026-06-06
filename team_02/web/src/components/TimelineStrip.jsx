import { useState } from "react";
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
      {conflicts > 0 && (
        <span className="tl-conflict-dot" title={`${conflicts} ${conflicts === 1 ? "room has" : "rooms have"} a comfort conflict`}>
          {conflicts}
        </span>
      )}
    </span>
  );
}

function TurnChip({ turn, active, onSelect }) {
  const icon = ACTION_ICONS[turn.action] || "○";
  return (
    <div className={"tl-chip" + (active ? " active" : "")} onClick={() => onSelect(turn.id)}>
      <span className="tl-chip-icon">{icon}</span>
      <span className="tl-chip-label">{turn.label}</span>
      <MiniRing score={turn.avgScore} conflicts={turn.conflictCount} />
    </div>
  );
}

export default function TimelineStrip({ turns, activeTurnId, onSelect }) {
  const [open, setOpen] = useState(true);
  if (!turns || !turns.length) return null;
  const last = turns[turns.length - 1];
  return (
    <div className={"timeline-strip" + (open ? " open" : " collapsed")}>
      <button className="tl-toggle" onClick={() => setOpen((o) => !o)} title={open ? "hide timeline" : "show timeline"}>
        {open ? "▾" : "▴"} timeline
      </button>
      {open ? (
        <div className="tl-chips-row">
          {turns.map((turn) => (
            <TurnChip key={turn.id} turn={turn} active={turn.id === activeTurnId} onSelect={onSelect} />
          ))}
        </div>
      ) : (
        <span className="tl-collapsed-label">{turns.length} {turns.length === 1 ? "turn" : "turns"} · {last.label}</span>
      )}
    </div>
  );
}
