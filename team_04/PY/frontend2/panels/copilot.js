// Right panel: GitHub Copilot-style chat. Renders transcript + action buttons +
// input. Delegates message handling to copilotClient (set via initCopilot).

import { getState, setState, subscribe } from "../core/store.js";
import { shouldShowInstantly } from "../core/responseFormatter.js";

let onSend = async () => {};
let busy = false;
let typedCount = 0;       // how many assistant messages have finished typing
let typingTimer = null;   // active typewriter interval
let typingActive = false; // a typewriter is currently running

// Minimal, safe markdown: **bold**, *italic*, `code`, and newlines.
function fmt(text) {
  const esc = String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return esc
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br/>");
}

// "How I understood this" — a small panel under an assistant message that reveals
// the 3-layer reasoning the AI just did (understand → choose → validate). All values
// are REAL fields from the manipulation response; nothing is invented. Collapsible so
// it stays out of the way until the user (or a curious professor) expands it.
function reasoningPanel(meta) {
  const esc = (v) => String(v == null ? "—" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const ok = meta.validation === "passed";
  const sourceBadge = meta.source === "AI language model"
    ? `<span class="rz-badge rz-ai">🧠 ${esc(meta.source)}</span>`
    : `<span class="rz-badge">${esc(meta.source)}</span>`;

  // Real per-check verdict from validate_design (only when we validated against a site).
  const checks = Array.isArray(meta.checks) ? meta.checks : [];
  const checkRows = checks.length
    ? `<div class="rz-checks">` + checks.map((c) =>
        `<span class="rz-chk ${c.passed ? "rz-ok" : "rz-no"}" title="${esc(c.message)}">`
        + `${c.passed ? "✓" : "✗"} ${esc(c.name.replace(/_/g, " "))}</span>`).join("") + `</div>`
    : "";
  // Self-debug attempts (the geometry was auto-corrected back into the site).
  const dbg = Array.isArray(meta.selfDebug) ? meta.selfDebug : [];
  const fixed = dbg.some((l) => /attempt|valid after fix|moved|shrank|nudged|rescaled/i.test(l));
  const dbgRow = fixed
    ? `<div class="rz-debug">🛠 Self-corrected: ${dbg.filter((l) => /attempt|fix/i.test(l)).map(esc).join(" · ") || "geometry repaired"}</div>`
    : "";

  return `
    <details class="reasoning">
      <summary><span class="rz-spark">✦</span> How I understood this</summary>
      <div class="rz-body">
        <div class="rz-step"><span class="rz-k">1 · Understood</span>
          <span class="rz-v">${esc(meta.intent)} ${sourceBadge}</span></div>
        <div class="rz-arrow">↓</div>
        <div class="rz-step"><span class="rz-k">2 · Chose operation</span>
          <span class="rz-v"><code>${esc(meta.operation)}</code></span></div>
        <div class="rz-arrow">↓</div>
        <div class="rz-step"><span class="rz-k">3 · Validated</span>
          <span class="rz-v ${ok ? "rz-ok" : "rz-no"}">${ok ? "✓ valid" : esc(meta.validation)}</span></div>
        ${checkRows}
        ${dbgRow}
        ${meta.why ? `<div class="rz-why">${esc(meta.why)}</div>` : ""}
      </div>
    </details>`;
}

function renderMessages() {
  const scroll = document.getElementById("chat-scroll");
  if (!scroll) return;
  // Don't rebuild the transcript while a message is actively typing — that would
  // wipe the in-progress bubble. Renders resume once typing completes.
  if (typingActive) return;
  const s = getState();
  const msgs = s.messages;
  const assistantCount = msgs.filter((m) => m.role === "assistant").length;
  // The newest assistant message types out once; everything before it is static.
  const lastAssistantIdx = msgs.map((m) => m.role).lastIndexOf("assistant");
  const shouldType = !busy && assistantCount > typedCount && lastAssistantIdx >= 0 && !typingActive;

  scroll.innerHTML = "";
  msgs.forEach((m, i) => {
    const el = document.createElement("div");
    el.className = `msg ${m.role}`;
    const isTypingTarget = shouldType && i === lastAssistantIdx;
    el.innerHTML = `
      <div class="avatar">${m.role === "assistant" ? "✦" : "🧑"}</div>
      <div class="bubble">${isTypingTarget ? "" : fmt(m.text)}</div>
      ${m.meta && m.meta.kind === "reasoning" ? reasoningPanel(m.meta) : ""}`;
    scroll.appendChild(el);
    if (isTypingTarget) typewrite(el.querySelector(".bubble"), m.text, scroll);
  });
  if (busy) {
    const t = document.createElement("div");
    t.className = "msg assistant";
    // AI thinking orb with rotating rings + a thinking caption.
    t.innerHTML = `<div class="avatar">✦</div>
      <div class="bubble thinking-bubble">
        <span class="ai-orb"><i></i><i></i><i></i><b></b></span>
        <span class="thinking-text">Thinking<span>·</span><span>·</span><span>·</span></span>
      </div>`;
    scroll.appendChild(t);
  }
  scroll.scrollTop = scroll.scrollHeight;
}

// Reveal an assistant message. Short conversational replies animate (faster than
// before); long or structured/technical messages render INSTANTLY so the chat
// never crawls through a wall of text — those details live in the workspace anyway.
function typewrite(bubble, text, scroll) {
  if (typingTimer) { clearInterval(typingTimer); typingTimer = null; }
  const msg = bubble.closest(".msg");

  // Instant path: long or list/header content shows at once.
  if (shouldShowInstantly(text)) {
    bubble.innerHTML = fmt(text);
    if (msg) msg.classList.remove("streaming");
    typedCount += 1;
    typingActive = false;
    if (scroll) scroll.scrollTop = scroll.scrollHeight;
    return;
  }

  typingActive = true;
  if (msg) msg.classList.add("streaming");
  // Faster typing: ~4ms/char (down from 6–14). Short replies feel snappy.
  const speed = 4;
  let i = 0;
  typingTimer = setInterval(() => {
    i += 2; // reveal 2 chars per tick for extra speed
    bubble.innerHTML = fmtPartial(text.slice(0, i));
    if (scroll) scroll.scrollTop = scroll.scrollHeight;
    if (i >= text.length) {
      clearInterval(typingTimer); typingTimer = null;
      bubble.innerHTML = fmt(text);
      if (msg) msg.classList.remove("streaming");
      typedCount += 1;     // this assistant message is now fully revealed
      typingActive = false;
      // run any render that was suppressed while typing (actions/status updates)
      render();
    }
  }, speed);
}

// Escape + newline-only formatting during the typewriter (avoid half-open tags).
function fmtPartial(text) {
  return String(text)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\n/g, "<br/>");
}

function renderActions() {
  const wrap = document.getElementById("chat-actions");
  if (!wrap) return;
  const s = getState();
  wrap.innerHTML = "";
  for (const a of s.actions || []) {
    const b = document.createElement("button");
    b.className = "action-btn" + (a.primary ? " primary" : "");
    b.textContent = a.label;
    b.addEventListener("click", () => onSend(a.message || a.label, a));
    wrap.appendChild(b);
  }
}

function renderStatus() {
  const el = document.getElementById("sb-status");
  const s = getState();
  if (el) {
    const statusParts = [s.status];
    if (s.selectedEdge) {
      statusParts.push(`| Selected: ${s.selectedEdge.label} (${s.selectedEdge.direction})`);
    }
    el.textContent = statusParts.join(" ");
  }
  const stageEl = document.getElementById("tb-stage");
  if (stageEl) stageEl.innerHTML = `<span class="dot">●</span> ${s.stage}`;
}

function render() {
  renderMessages();
  renderActions();
  renderStatus();
}

export function setBusy(v) {
  busy = v;
  renderMessages();
  const send = document.getElementById("chat-send");
  if (send) send.disabled = v;
  // Premium processing feedback on the center stage while the AI works.
  const proc = document.getElementById("center-processing");
  if (proc) proc.classList.toggle("hidden", !v);
  // Drive the combined scanning state: Copilot processing -> scan ON; when the
  // response completes -> scan OFF. This covers every prompt round-trip
  // (location lookup, boundary analysis, optimization, generic chat).
  // On completion we also clear the granular phase flags as a safety net so the
  // scan can never get stuck on if a precise stop-event didn't fire.
  if (v) {
    setState({ isCopilotThinking: true });
  } else {
    setState({
      isCopilotThinking: false,
      isLocatingSite: false,
      isBoundaryActivating: false,
      isAnalyzingBoundary: false,
      isOptimizing: false,
    });
  }
}

export function initCopilot(sendHandler) {
  onSend = sendHandler;
  const panel = document.getElementById("copilot");
  panel.innerHTML = `
    <div class="copilot-header">
      <span class="ico">✦</span>
      <span class="title">TerraPilot Copilot</span>
      <span class="sub">AI-driven workflow</span>
    </div>
    <div id="chat-scroll" class="chat-scroll"></div>
    <div id="chat-actions" class="chat-actions"></div>
    <div class="chat-input-wrap">
      <div class="chat-input-row">
        <textarea id="chat-input" class="chat-input" placeholder="Message TerraPilot…" rows="1"></textarea>
        <button id="chat-send" class="chat-send" title="Send">➤</button>
      </div>
    </div>`;

  const input = panel.querySelector("#chat-input");
  const send = panel.querySelector("#chat-send");

  const submit = () => {
    const text = input.value.trim();
    if (!text || busy) return;
    input.value = "";
    input.style.height = "38px";
    onSend(text);
  };
  send.addEventListener("click", submit);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  });
  input.addEventListener("input", () => {
    input.style.height = "38px";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  });

  render();
  subscribe(render);
}
