// API client — replaces the QWebChannel bridge (window.bridge.* + window.receive*).
// Each function calls a FastAPI endpoint built in Phase 2 (api/server.py) and
// returns the JSON shaped by api/contracts.py. The session_id is stored locally
// and sent on every call so the server can keep per-visitor state.

const BASE = import.meta.env.VITE_API_BASE || "";

const SID_KEY = "sensi_session_id";

export function getSessionId() {
  return localStorage.getItem(SID_KEY) || null;
}

function setSessionId(sid) {
  if (sid) localStorage.setItem(SID_KEY, sid);
}

export function clearSessionId() {
  localStorage.removeItem(SID_KEY);
}

async function post(path, body = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: getSessionId(), ...body }),
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  const data = await res.json();
  if (data.session_id) setSessionId(data.session_id);
  return data;
}

// ── Plain request/response endpoints ──────────────────────────────────────
export const init             = ()             => post("/api/init");
export const sendMessage      = (text)         => post("/api/message", { text });
export const resetPersona     = ()             => post("/api/reset-persona");
export const saveInspirePicks = (round, urls)  => post("/api/inspire/picks", { round, urls });
export const buildMoodboard   = (senseCounts)  => post("/api/inspire/moodboard", { sense_counts: senseCounts });
export const profileChat      = (text)         => post("/api/profile-chat", { text });
export const getLayout        = ()             => post("/api/layout");

// ── SSE: inspire rounds stream progress, then a final result ──────────────
// callbacks: { onSession(id), onProgress(msg), onResult(data) }
async function inspireStream(path, body, { onSession, onProgress, onResult }) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: getSessionId(), ...body }),
  });
  if (!res.ok || !res.body) throw new Error(`${path} failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "message";
      let dataStr = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      if (!dataStr) continue;
      const payload = JSON.parse(dataStr);
      if (event === "session" && payload.session_id) {
        setSessionId(payload.session_id);
        onSession && onSession(payload.session_id);
      } else if (event === "progress") {
        onProgress && onProgress(payload.message);
      } else if (event === "result") {
        onResult && onResult(payload);
      }
    }
  }
}

export const prepareInspire = (text, b64s, round, cbs) =>
  inspireStream("/api/inspire/prepare", { text, b64s, round }, cbs);

export const refineInspire = (refineDesc, round, cbs) =>
  inspireStream("/api/inspire/refine", { refine_desc: refineDesc, round }, cbs);
