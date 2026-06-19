import { useEffect, useMemo, useState } from "react";
import { SelectionProvider } from "../lib/selection.jsx";
import SensePlan from "./SensePlan.jsx";

// DEV-ONLY rendering harness (gated behind ?plan=<id> in main.jsx). Renders the real
// SensePlan against a static layout fixture from /public/dev-layouts so the plan
// linework can be verified across all four example layouts without the LLM/onboarding
// flow. Not imported by the production App. Safe to delete after the rendering session.
const IDS = ["201", "202", "203", "204"];
const SENSE_KEYS = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"];

// Deterministic pseudo-score from a room name so the comfort lens lights up (no agent).
function hashScore(name, salt = 0) {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < name.length; i++) { h = Math.imul(h ^ name.charCodeAt(i), 16777619); }
  return 0.3 + ((h >>> 0) % 1000) / 1000 * 0.65; // 0.30..0.95
}

export default function DevPlan() {
  const initial = new URLSearchParams(location.search).get("plan");
  const [id, setId] = useState(IDS.includes(initial) ? initial : "202");
  const [layout, setLayout] = useState(null);
  const [comfort, setComfort] = useState(false);

  useEffect(() => {
    let alive = true;
    setLayout(null);
    fetch(`/dev-layouts/layout_${id}.json`)
      .then((r) => r.json())
      .then((d) => { if (alive) setLayout(d); })
      .catch(() => {});
    return () => { alive = false; };
  }, [id]);

  // Fabricated scored rooms (comfort lens only — plan layer ignores these).
  const rooms = useMemo(() => (layout?.rooms || []).map((r) => ({
    roomName: r.name,
    overallScore: hashScore(r.name),
    comfortScores: Object.fromEntries(SENSE_KEYS.map((k, i) => [k, hashScore(r.name, i + 1)])),
  })), [layout]);

  const layers = { plan: true, comfort, graph: false, material: false };

  return (
    <div style={{ position: "fixed", inset: 0, background: "var(--bg)", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", gap: 8, padding: 10, alignItems: "center", fontFamily: "var(--font-mono)", fontSize: 12, color: "rgba(var(--fg-rgb),0.7)" }}>
        <span style={{ letterSpacing: ".12em", textTransform: "uppercase", opacity: 0.6 }}>dev plan</span>
        {IDS.map((x) => (
          <button key={x} onClick={() => setId(x)}
            style={{ padding: "3px 10px", borderRadius: 999, cursor: "pointer", fontFamily: "inherit",
              border: "1px solid rgba(var(--fg-rgb),0.18)", background: x === id ? "rgba(var(--fg-rgb),0.12)" : "transparent",
              color: x === id ? "rgba(var(--fg-rgb),0.95)" : "rgba(var(--fg-rgb),0.6)" }}>{x}</button>
        ))}
        <label style={{ marginLeft: 12, display: "inline-flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
          <input type="checkbox" checked={comfort} onChange={(e) => setComfort(e.target.checked)} /> comfort lens
        </label>
        <span style={{ marginLeft: "auto", opacity: 0.5 }}>{layout ? `${layout.layoutId || id} · ${layout.rooms?.length || 0} rooms` : "loading…"}</span>
      </div>
      <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
        <SelectionProvider>
          {layout && <SensePlan layoutData={layout} rooms={rooms} layoutId={id} layers={layers} />}
        </SelectionProvider>
      </div>
    </div>
  );
}
