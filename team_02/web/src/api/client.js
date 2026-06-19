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
export const renderRoom       = (roomName, force = false) => post("/api/render-room", { room_name: roomName, force });
export const getReport        = ()             => post("/api/report");
// Before/after is always initial (un-edited, on-disk) → current. There is no
// "last edit only" compare — that semantic was removed to keep one source of truth.
export const compareInitial   = (force = false) => post("/api/compare-initial", { force });

// Checkpoints (Task 3): commit the working draft as a milestone; restore rolls back to one.
export const commit           = (label)        => post("/api/commit", { label });
export const restore          = (checkpointId) => post("/api/restore", { checkpoint_id: checkpointId });
// View a checkpoint's scored state for review (non-destructive).
export const viewCheckpoint   = (checkpointId) => post("/api/checkpoint", { checkpoint_id: checkpointId });

// ── SSE: shared frame reader ──────────────────────────────────────────────
// POSTs body, reads the text/event-stream response, and dispatches each frame to
// handlers[event](payload). `signal` (optional) lets the caller abort mid-stream.
async function streamSSE(path, body, handlers, signal) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: getSessionId(), ...body }),
    signal,
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
      let payload;
      try { payload = JSON.parse(dataStr); } catch { continue; }
      const fn = handlers[event];
      if (fn) fn(payload);
    }
  }
}

// inspire rounds: stream progress, then a final result.
// callbacks: { onSession(id), onProgress(msg), onResult(data) }
function inspireStream(path, body, { onSession, onProgress, onResult }) {
  return streamSSE(path, body, {
    session: (p) => { if (p.session_id) { setSessionId(p.session_id); onSession && onSession(p.session_id); } },
    progress: (p) => onProgress && onProgress(p.message),
    result: (p) => onResult && onResult(p),
  });
}

export const prepareInspire = (text, b64s, round, cbs) =>
  inspireStream("/api/inspire/prepare", { text, b64s, round }, cbs);

export const refineInspire = (refineDesc, round, cbs) =>
  inspireStream("/api/inspire/refine", { refine_desc: refineDesc, round }, cbs);

// ── SSE: streaming agent turn (progress labels + token-by-token answer) ─────
// Mirrors sendMessage but streams. callbacks (all optional):
//   onProgress({node, message})  a step finished — human label for the UI
//   onMessageStart()             begin/replace the streamed answer buffer
//   onToken(text)                a chunk of the final answer
//   onResult(data)               same payload shape as sendMessage
//   onError(message)             the turn failed gracefully (server-reported)
// Pass an AbortController.signal to cancel mid-turn.
export function sendMessageStream(text, cbs = {}, signal) {
  const { onSession, onProgress, onMessageStart, onToken, onResult, onError } = cbs;
  return streamSSE("/api/message/stream", { text }, {
    session: (p) => { if (p.session_id) { setSessionId(p.session_id); onSession && onSession(p.session_id); } },
    progress: (p) => onProgress && onProgress(p),
    message_start: () => onMessageStart && onMessageStart(),
    token: (p) => onToken && onToken(p.text),
    result: (p) => { if (p.session_id) setSessionId(p.session_id); onResult && onResult(p); },
    error: (p) => onError && onError(p.message),
  }, signal);
}

// Layout management
export const selectLayout = (layout_id) => post("/api/layout/select", { layout_id });

export const uploadLayout = async (file) => {
  const text = await file.text();
  const res = await fetch(`${BASE}/api/layout/upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: getSessionId(), layout_json: text }),
  });
  if (!res.ok) throw new Error(`layout upload failed: ${res.status}`);
  const data = await res.json();
  if (data.session_id) setSessionId(data.session_id);
  return data;
};
