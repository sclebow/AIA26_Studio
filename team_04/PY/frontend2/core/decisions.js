// Decision recorder — the single place every workflow action logs to the real
// project timeline. Appends to store.decisionHistory immediately (so the graph is
// live) and syncs the entry to the backend session so export + replay read the
// same history. Never fabricates steps — only what actually happened.

import { getState, setState } from "./store.js";
import { api } from "./api.js";

let _seq = 0;

// Record one decision. stage/action are required; the rest optional.
//   recordDecision("shape", "shape_generated", { input, result, data })
export function recordDecision(stage, action, { input = null, result = "", data = {} } = {}) {
  _seq += 1;
  const entry = {
    step_id: `step_${String(_seq).padStart(3, "0")}`,
    timestamp: new Date().toISOString(),
    stage,
    action,
    input,
    result,
    data,
  };
  setState({ decisionHistory: [...(getState().decisionHistory || []), entry] });

  // Best-effort backend sync (don't block the UI on it).
  const { sessionId } = getState();
  if (sessionId && api.agent.addDecision) {
    api.agent.addDecision(sessionId, entry).catch(() => {});
  }
  return entry;
}

export function getDecisionHistory() {
  return getState().decisionHistory || [];
}

export function resetDecisionHistory() {
  _seq = 0;
  setState({ decisionHistory: [] });
}
