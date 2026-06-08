import { useState } from "react";
import SenseDeltaPills from "./SenseDeltaPills.jsx";

/*
 * CommitBar — the per-message commit affordance (Task 3). Appears under the latest
 * Sensi reply when the working draft has uncommitted edits. Shows the score change
 * since the last checkpoint (instant, no images) and commits the cumulative draft as
 * a new milestone. Deliberately quiet — a thin divider, not a boxed callout.
 */
export default function CommitBar({ delta = {}, onCommit }) {
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const hasDelta = delta && Object.keys(delta).length > 0;

  const commit = async () => {
    if (busy) return;
    setBusy(true);
    try { await onCommit?.(label.trim()); } finally { setBusy(false); setLabel(""); }
  };

  return (
    <div style={{
      marginTop: 10, paddingTop: 10,
      borderTop: "1px solid rgba(var(--fg-rgb),0.12)",
      display: "flex", flexDirection: "column", gap: 8,
    }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "0.04em",
        textTransform: "uppercase", color: "rgba(var(--fg-rgb),0.55)" }}>
        uncommitted changes · since the last checkpoint
      </span>
      {hasDelta && <SenseDeltaPills deltas={delta} style={{ marginTop: 2 }} />}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") commit(); }}
          placeholder="name this milestone (optional)"
          style={{
            flex: "1 1 160px", minWidth: 120, fontSize: 13,
            padding: "6px 10px", borderRadius: 8,
            border: "1px solid rgba(var(--fg-rgb),0.15)",
            background: "rgba(var(--fg-rgb),0.04)", color: "inherit",
          }}
        />
        <button className="layer-pill" disabled={busy} onClick={commit}>
          {busy ? "committing…" : "✓ commit checkpoint"}
        </button>
      </div>
    </div>
  );
}
