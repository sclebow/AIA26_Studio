import { useState } from "react";
import { scoreColor } from "../lib/constants.js";

// Checkpoints strip (Task 3) — the renamed timeline. Shows only COMMITTED milestones
// (not every turn). Checkpoint 0 is the initial layout; click a chip to view it, then
// restore to roll the working draft back to that milestone.

function MiniRing({ score, conflicts }) {
  if (score == null) return <span className="tl-mini-ring" style={{ opacity: 0.5 }}>—</span>;
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

function CheckpointChip({ cp, active, onSelect }) {
  return (
    <div className={"tl-chip" + (active ? " active" : "")} onClick={() => onSelect(cp.id)} title={cp.label}>
      <span className="tl-chip-icon">{cp.is_initial ? "◉" : "✓"}</span>
      <span className="tl-chip-label">{cp.label}</span>
      <MiniRing score={cp.avg_score} conflicts={cp.conflict_count} />
    </div>
  );
}

export default function CheckpointsStrip({ checkpoints = [], onRestore }) {
  const [open, setOpen] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  if (!checkpoints.length) return null;

  const selected = checkpoints.find((c) => c.id === selectedId) || null;

  return (
    <div className={"timeline-strip" + (open ? " open" : " collapsed")}>
      <button className="tl-toggle" onClick={() => setOpen((o) => !o)} title={open ? "hide checkpoints" : "show checkpoints"}>
        {open ? "▾" : "▴"} checkpoints
      </button>
      {open ? (
        <div className="tl-chips-row">
          {checkpoints.map((cp) => (
            <CheckpointChip key={cp.id} cp={cp} active={cp.id === selectedId}
              onSelect={(id) => setSelectedId(id === selectedId ? null : id)} />
          ))}
          {selected && (
            <button className="layer-pill" style={{ marginLeft: 8, whiteSpace: "nowrap" }}
              onClick={() => {
                if (window.confirm(`Restore to "${selected.label}"? This discards any uncommitted edits.`)) {
                  onRestore?.(selected.id);
                  setSelectedId(null);
                }
              }}>
              ↺ restore
            </button>
          )}
        </div>
      ) : (
        <span className="tl-collapsed-label">
          {checkpoints.length} {checkpoints.length === 1 ? "checkpoint" : "checkpoints"}
        </span>
      )}
    </div>
  );
}
