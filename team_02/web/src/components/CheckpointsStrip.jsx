import { useState } from "react";
import { scoreColor } from "../lib/constants.js";
import CheckpointGraph from "./CheckpointGraph.jsx";

// Checkpoints strip (Task 3) — the renamed timeline. Shows only COMMITTED milestones
// (not every turn). Checkpoint 0 is the initial layout; click a chip to view it, then
// restore to roll the working draft back to that milestone.
//
// Session 8: the slim chip strip is the compact index; the "⤢ graph" control expands a
// GitHub-style sense-line graph (CheckpointGraph) as a popover above it — both share the
// same view/restore handlers, so focusing in one reflects in the other.

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

export default function CheckpointsStrip({ checkpoints = [], liveHead = null, onRestore, onView, viewedId = null }) {
  const [open, setOpen] = useState(true);
  const [graphOpen, setGraphOpen] = useState(false);
  if (!checkpoints.length) return null;

  // Single source of truth = the parent's viewed checkpoint. Click a chip to review
  // its scores on the canvas; restore acts on the one you're viewing.
  const viewed = checkpoints.find((c) => c.id === viewedId) || null;

  return (
    <div className={"timeline-strip" + (open ? " open" : " collapsed")}>
      {graphOpen && (
        <div className="cg-popover">
          <CheckpointGraph checkpoints={checkpoints} liveHead={liveHead} viewedId={viewedId}
            onView={onView} onRestore={onRestore} onClose={() => setGraphOpen(false)} />
        </div>
      )}
      <button className="tl-toggle" onClick={() => setOpen((o) => !o)} title={open ? "hide checkpoints" : "show checkpoints"}>
        {open ? "▾" : "▴"} checkpoints
      </button>
      {open ? (
        <div className="tl-chips-row">
          {checkpoints.map((cp) => (
            <CheckpointChip key={cp.id} cp={cp} active={cp.id === viewedId}
              onSelect={(id) => onView?.(id)} />
          ))}
          {viewed && (
            <button className="layer-pill" style={{ marginLeft: 8, whiteSpace: "nowrap" }}
              onClick={() => {
                if (window.confirm(`Restore to "${viewed.label}"? This discards any uncommitted edits.`)) {
                  onRestore?.(viewed.id);
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
      <button className={"tl-graph-toggle" + (graphOpen ? " active" : "")} onClick={() => setGraphOpen((g) => !g)}
        title={graphOpen ? "hide the sense graph" : "see the senses rise and fall across checkpoints"}>
        {graphOpen ? "✕ graph" : "⤢ graph"}
      </button>
    </div>
  );
}
