// Copilot response formatter — keeps the chat panel concise.
//
// Detailed reports (urban context, edge intelligence, optimization tables) live
// in the CENTER workspace panels. The chat is a terse assistant: 1–3 short
// sentences, no repeated paragraphs, no duplicated edge reports. This module
// collapses long/verbose assistant text into the next required action only.

// Recognizable long-report signatures → a one-line stand-in. The detailed
// content is already rendered in the workspace, so we never repeat it in chat.
const REPORT_SIGNATURES = [
  {
    // Urban context report (edge distances, opportunities, scores dump)
    test: (t) =>
      /urban context|context (analysis|summary|report)/i.test(t) &&
      (/edge/i.test(t) || /opportunit/i.test(t) || /walkability|transit|accessibility/i.test(t)),
    replacement:
      "Context analysis complete. Key scores and the edge report are shown in the workspace.",
  },
  {
    // Optimization results dump (ranked options, scores, FAR table)
    test: (t) =>
      /optimi[sz]ation|nsga|ranked (options|design)/i.test(t) &&
      /(score|far|option\s*\d|rank)/i.test(t) &&
      t.length > 240,
    replacement:
      "Optimization complete. Ranked options are shown in the workspace — tell me which to take forward.",
  },
];

// Collapse runs of duplicated lines/paragraphs (the "types the same thing again
// and again" problem). Compares normalized lines and drops exact repeats.
function dedupeLines(text) {
  const lines = String(text).split("\n");
  const out = [];
  const seen = new Set();
  for (const line of lines) {
    const norm = line.trim().toLowerCase().replace(/\s+/g, " ");
    if (norm === "") {
      // keep a single blank line between blocks, collapse multiples
      if (out.length && out[out.length - 1] !== "") out.push("");
      continue;
    }
    if (seen.has(norm)) continue; // duplicate paragraph/line — drop it
    seen.add(norm);
    out.push(line);
  }
  // strip trailing blank
  while (out.length && out[out.length - 1] === "") out.pop();
  return out.join("\n");
}

// Remove repeated per-edge report blocks ("North Edge … East Edge …") that the
// chat sometimes echoes — those belong in the AI Context Report panel only.
function stripEdgeReportBlocks(text) {
  // If the message contains 3+ compass-edge headers, it's an edge report dump.
  const edgeHeaders = (text.match(/\b(north|south|east|west|northeast|northwest|southeast|southwest)\s+edge\b/gi) || []).length;
  if (edgeHeaders >= 3) {
    return "Edge intelligence updated — see the AI Context Report in the workspace.";
  }
  return text;
}

// Keep at most N sentences (default 3) for short conversational replies. Long
// technical/report messages are handled by the signatures above and skipped here.
function clampSentences(text, max = 3) {
  // Don't clamp messages that are clearly a single short status line.
  const sentences = text.match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g);
  if (!sentences || sentences.length <= max) return text;
  return sentences.slice(0, max).join("").trim();
}

/**
 * shortenCopilotResponse(message) — the single entry point.
 * Applied to every assistant chat message before it is displayed:
 *   1. swap a known long-report dump for its one-line stand-in,
 *   2. collapse duplicated edge-report blocks,
 *   3. remove repeated paragraphs/lines,
 *   4. clamp to a few sentences for ordinary replies.
 * User messages and already-short messages pass through unchanged.
 */
export function shortenCopilotResponse(message) {
  if (typeof message !== "string" || !message.trim()) return message;

  // 1) Known report signatures → concise stand-in (detail stays in workspace).
  for (const sig of REPORT_SIGNATURES) {
    if (sig.test(message)) return sig.replacement;
  }

  // 2) Collapse multi-edge report dumps.
  let out = stripEdgeReportBlocks(message);

  // 3) Drop duplicated paragraphs/lines.
  out = dedupeLines(out);

  // 4) For ordinary prose (no markdown lists/headers), clamp sentence count.
  const hasStructure = /(^|\n)\s*([*\-•]|#{1,6}\s|\d+\.)/.test(out);
  if (!hasStructure) {
    out = clampSentences(out, 3);
  }

  return out;
}

// True for messages that should appear INSTANTLY (no typewriter): long or
// structured technical content. Short conversational replies animate.
export function shouldShowInstantly(message) {
  if (typeof message !== "string") return false;
  if (message.length > 160) return true;
  if (/(^|\n)\s*([*\-•]|#{1,6}\s|\d+\.)/.test(message)) return true; // lists/headers
  return false;
}
