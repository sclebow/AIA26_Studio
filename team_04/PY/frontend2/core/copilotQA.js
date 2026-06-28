// Copilot Question-Answering layer.
//
// Makes TerraPilot Copilot answer the user's QUESTIONS directly from real app
// state instead of falling through to the agent SSE (which only ever says
// "I finished that step"). Three response modes are detected here:
//
//   1. QUESTION    — "did you...", "what is...", "is the...", "how much..."
//   2. EXPLANATION — "why...", "explain...", "what happened"
//   3. NEXT-STEP   — "what now", "next step", "what should I do" (handed back to
//                    the existing navigation handler — not answered here)
//
// COMMANDS ("move 5m north", "add 2 floors", "I want more daylight") are NOT
// questions and are deliberately left for the existing command/feedback routing.
//
// Every answer is built ONLY from confirmed state (decisionHistory, context
// scores, optimization result, manipulation history). When the state can't
// confirm the answer, we say so plainly — we never pretend an action happened.

import { getState } from "./store.js";

// ---------------------------------------------------------------------------
// Intent detection
// ---------------------------------------------------------------------------

// A command/critique that should NOT be treated as a question even if phrased
// oddly. Keeps "move it north" out of the QA path.
const COMMAND_RX =
  /\b(move|rotate|scale|add|remove|make|set|place|align|stretch|compress|carve|create|open|reduce|increase|extend|shrink|enlarge|optimize|optimise|generate|export|compare|evaluate|select|save|discard)\b/i;

const QUESTION_WORD_RX =
  /\b(did|do|does|is|are|was|were|has|have|had|can|could|will|would|should|what|which|where|when|how|why|whats|what's|wh' s)\b/i;

const EXPLAIN_RX = /\b(why|explain|what happened|how come|reason|because)\b/i;
const NEXTSTEP_RX =
  /\b(next step|what now|what next|what should i do|where to now|whats next|what's next|how do i proceed)\b/i;

// Classify the message. Returns "question" | "explanation" | "nextstep" | null.
// null = not a question; let the existing command/feedback/navigation routing run.
export function classifyMessage(message) {
  const t = (message || "").trim();
  if (!t) return null;
  const low = t.toLowerCase();

  if (NEXTSTEP_RX.test(low)) return "nextstep";

  const endsWithQ = /\?\s*$/.test(t);
  const startsQuestiony = QUESTION_WORD_RX.test(low.split(/\s+/).slice(0, 3).join(" "));

  // "why/explain ..." is an explanation request (answer it, even without "?").
  if (EXPLAIN_RX.test(low) && (endsWithQ || startsQuestiony || /^why|^explain/i.test(low))) {
    return "explanation";
  }

  // A real question: ends with "?" OR opens with a question word. But if it ALSO
  // looks like a direct command verb at the very start ("move the building?"),
  // prefer the command path so geometry still happens.
  const startsWithCommand = COMMAND_RX.test(low.split(/\s+/).slice(0, 2).join(" "));
  if ((endsWithQ || startsQuestiony) && !startsWithCommand) return "question";

  return null;
}

// ---------------------------------------------------------------------------
// State helpers — every fact comes from real state, never fabricated.
// ---------------------------------------------------------------------------

function history() {
  return getState().decisionHistory || [];
}

// The most recent decision entry (the "last action performed").
function lastAction() {
  const h = history();
  return h.length ? h[h.length - 1] : null;
}

// All editing/manipulation entries, oldest→newest.
function manipulationHistory() {
  return history().filter((e) => e.stage === "editing");
}

// Did any manipulation actually MOVE the building? Looks for move/place/reposition
// ops in the recorded manipulation history (accepted only).
function lastMoveEntry() {
  const moves = history().filter((e) => {
    const a = (e.action || "").toLowerCase();
    if (/reject/.test(a)) return false;
    if (/move|place|reposition|context/.test(a)) return true;
    // architectural_feedback whose accepted ops include a move/place
    const ops = (e.data?.actions || []).filter((o) => o.accepted).map((o) => (o.op || "").toLowerCase());
    return ops.some((op) => /move|place|context/.test(op));
  });
  return moves.length ? moves[moves.length - 1] : null;
}

// The most recent noise score we can confirm (from an evaluation or optimization).
// Returns { value, source } or null if no noise data exists yet.
function noiseScore() {
  // 1. From the latest design evaluation recorded in history.
  const evals = history().filter((e) => e.stage === "evaluation" && e.data?.data);
  for (let i = evals.length - 1; i >= 0; i--) {
    const s = evals[i].data.data;
    if (s && s.noise != null) return { value: s.noise, source: "the last design evaluation" };
  }
  // 2. From the top optimization option's objective scores.
  const opt = getState().optimizationResult;
  const top = opt?.options?.[0];
  const n = top?.objective_scores?.noise ?? top?.objective_breakdown?.noise;
  if (n != null) return { value: n, source: "the top optimization option" };
  // 3. From comparison options.
  const comp = (getState().comparisonOptions || [])[0];
  const cn = comp?.objective_scores?.noise;
  if (cn != null) return { value: cn, source: "the compared options" };
  return null;
}

// Whether optimization has been run (and how many options it produced).
function optimizationStatus() {
  const opt = getState().optimizationResult;
  const ranOpt = history().some((e) => e.stage === "optimization" && /run|generated/.test(e.action || ""));
  const count = opt?.options?.length || 0;
  return { ran: ranOpt || count > 0, count };
}

// Short human label of the last action for explanations.
function lastActionLabel() {
  const la = lastAction();
  if (!la) return null;
  return la.result || (la.action || "").replace(/_/g, " ");
}

// ---------------------------------------------------------------------------
// Answer builders — one per question family. Each returns a short string, or
// null if this builder doesn't apply to the message.
// ---------------------------------------------------------------------------

function answerDidYouMove(low) {
  // Only a MOVE question: needs a move/relocation verb or a spatial "away/closer".
  // "noise" alone is NOT enough (that's a noise-score question, handled below).
  if (!/\b(move|moved|moving|relocat|reposition|repositioned|shift|shifted)\b|away from|closer to/.test(low)) return null;
  if (!/\b(did|have|has|was|were|is)\b/.test(low) && !/\?$/.test(low)) return null;

  const move = lastMoveEntry();
  const aboutNoise = /noise|quiet|road|highway|traffic|loud/.test(low);

  if (!move) {
    // No move happened. Be specific about what DID happen instead.
    const last = lastActionLabel();
    let msg = "No — the building hasn't been moved.";
    if (last) msg += ` The last action was: ${last}.`;
    if (aboutNoise) {
      const ns = noiseScore();
      msg += ns
        ? ` Current noise score is ${ns.value} (from ${ns.source}). Run optimization to reduce noise exposure.`
        : " I don't have a noise score yet — run optimization or evaluate the design to measure noise.";
    }
    return msg;
  }

  // A move did happen.
  let msg = `Yes — the building was repositioned (${move.result || move.action.replace(/_/g, " ")}).`;
  if (aboutNoise) {
    const ns = noiseScore();
    if (ns) {
      msg += ` Current noise score is ${ns.value} (from ${ns.source}).`;
    } else {
      msg += " I can't confirm the noise change from the current data — evaluate or optimize to measure noise before/after.";
    }
  }
  return msg;
}

function answerNoise(low) {
  if (!/\bnoise|acoustic|quiet|loud|traffic\b/.test(low)) return null;
  const ns = noiseScore();
  if (!ns) {
    return "I can't confirm a noise score from the current data yet. Run optimization or evaluate the design, and I'll report the noise exposure.";
  }
  return `The noise score is ${ns.value} (from ${ns.source}). Higher is better (less noise exposure).`;
}

function answerOptimization(low) {
  if (!/\boptimi[sz]|optimized|ranked|best option\b/.test(low)) return null;
  const { ran, count } = optimizationStatus();
  if (!ran) return "Optimization hasn't been run yet. Type *optimize* to rank placement options for the current building.";
  const opt = getState().optimizationResult;
  const top = opt?.options?.[0];
  let msg = `Yes — optimization has run and produced ${count} ranked option${count > 1 ? "s" : ""}.`;
  if (top?.score != null) msg += ` The top option scores ${Number(top.score).toFixed(2)}.`;
  return msg;
}

function answerLastAction(low) {
  if (!/\blast|just|recent|what did you do|what happened|previous\b/.test(low)) return null;
  const la = lastAction();
  if (!la) return "Nothing has been done yet in this session — start by setting the site, then generate a shape.";
  const when = la.stage ? ` (${la.stage} stage)` : "";
  return `The last action was: ${la.result || la.action.replace(/_/g, " ")}${when}.`;
}

function answerContext(low) {
  if (!/\bcontext|metro|park|road|edge|surroundings|nearby|transit|walkab\b/.test(low)) return null;
  const ctx = getState().context;
  const scores = getState().contextScores;
  if (!ctx && !scores) {
    return "I can't confirm anything about the context — Urban Context hasn't been generated yet. Run it first.";
  }
  if (scores) {
    const parts = [];
    if (scores.transit != null) parts.push(`transit ${scores.transit}`);
    if (scores.walkability != null) parts.push(`walkability ${scores.walkability}`);
    if (scores.greenSpace != null) parts.push(`green space ${scores.greenSpace}`);
    if (scores.retail != null) parts.push(`retail ${scores.retail}`);
    if (parts.length) return `From the urban context analysis: ${parts.join(", ")} (0–100, higher is better).`;
  }
  return "Urban context is loaded. Ask about a specific feature (transit, walkability, green space) for the score.";
}

function answerExplanation(low) {
  // "why did the building rotate?", "explain the last change"
  const la = lastAction();
  if (!la) return "There's nothing to explain yet — no action has been taken in this session.";
  const reason = la.data?.reason || la.result || (la.action || "").replace(/_/g, " ");
  let msg = `The last action — ${(la.action || "").replace(/_/g, " ")} — ${reason ? `did this: ${reason}.` : "completed."}`;
  const obs = la.data?.observations;
  if (obs && obs.length) msg += ` Reasoning: ${obs[0]}.`;
  return msg;
}

// ---------------------------------------------------------------------------
// Public entry: try to answer. Returns a string answer, or null to defer to the
// existing routing (commands / navigation / agent).
// ---------------------------------------------------------------------------

export function tryAnswer(message) {
  const kind = classifyMessage(message);
  if (kind === null || kind === "nextstep") return null; // nextstep handled elsewhere

  const low = (message || "").toLowerCase();

  if (kind === "explanation") {
    return answerExplanation(low);
  }

  // QUESTION: walk the specific answer builders in priority order; first hit wins.
  const builders = [
    answerDidYouMove,
    answerNoise,
    answerOptimization,
    answerContext,
    answerLastAction,
  ];
  for (const b of builders) {
    const ans = b(low);
    if (ans) return ans;
  }

  // It's a question we recognise the SHAPE of but can't ground in data.
  return "I can't confirm that from the current data. Tell me what you'd like to do, or ask about the last action, noise score, optimization status, or context.";
}
