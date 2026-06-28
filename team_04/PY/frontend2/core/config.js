// Frontend2 runtime configuration.
//
// There is ONE real backend in this repo: the connection/ FastAPI app
// (team_04/PY/connection/app.py) — the notebook-validated Agent API. It exposes
// /sessions, /sessions/{id}/chat (SSE), /sessions/{id}/decisions,
// /sessions/{id}/explorer, /site/*, /export/*, /tools, and it also serves
// frontend2 itself at "/".
//
// Start it (from team_04/PY):
//     uvicorn connection.app:app --reload --port 8001
//
// If you open the UI from that same server (http://127.0.0.1:8001/), set
// AGENT_BASE to "" (same origin). If you serve frontend2 from elsewhere, point
// AGENT_BASE at the connection app's host:port. Override without editing this
// file via window.TERRAPILOT_AGENT_BASE before this module loads.
//
// Note: the legacy "TerraPilot Backend A" routes referenced by the dormant
// wrappers in core/api.js are NOT served by anything in this repo.

// Default to same-origin: the connection app serves frontend2 at "/", so the API
// lives on the same host:port. Override with window.TERRAPILOT_AGENT_BASE if you
// serve the UI from a different origin than the connection app.
const DEFAULT_AGENT_BASE = "";

// Allow an override injected by the host page (e.g. a <script> tag or env shim)
// without editing this file.
function resolveAgentBase() {
  if (typeof window !== "undefined" && typeof window.TERRAPILOT_AGENT_BASE === "string") {
    return window.TERRAPILOT_AGENT_BASE.replace(/\/+$/, "");
  }
  return DEFAULT_AGENT_BASE.replace(/\/+$/, "");
}

export const config = {
  // Base URL for Backend B (the notebook-validated agent API). "" = same origin.
  agentBase: resolveAgentBase(),
  // Base URL for Backend A (TerraPilot). It serves frontend2, so it is same-origin.
  terrapilotBase: "",
};

// Join a base URL with a path, tolerating a "" (same-origin) base.
export function agentUrl(path) {
  const base = config.agentBase;
  return base ? `${base}${path}` : path;
}
