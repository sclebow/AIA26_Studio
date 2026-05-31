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
  if (!turns || !turns.length) return null;
  return (
    <div className="timeline-strip">
      <div className="tl-chips-row">
        <span className="tl-label">timeline</span>
        {turns.map((turn) => (
          <TurnChip key={turn.id} turn={turn} active={turn.id === activeTurnId} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}
