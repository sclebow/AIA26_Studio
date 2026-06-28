// Conversation driver. Routes each user/action message to the part of the system
// that actually owns it:
//
//   * SITE / BOUNDARY stages  → handled locally by the map view + the real
//     site/boundary routes (api.agent.geocode / analyzeBoundary /
//     saveSessionBoundary). The core agent has no map workflow, so this stage is
//     frontend-driven with backend boundary analysis.
//   * SHAPES onward (generation, manipulation, optimization, decisions) → the
//     REAL agent backend via agentClient.streamChat (SSE /sessions/{id}/chat).
//
// There is no "/copilot" orchestrator backend in this repo, so nothing here
// calls one. The agent backend is the single source of truth for the design
// conversation; the site/boundary stage is the documented frontend-fallback.

import { api } from "./core/api.js";
import {
  getState,
  setState,
  pushMessage,
  setStatus,
  pushError,
} from "./core/store.js";
import { STAGES, STAGE_VIEW } from "./core/stages.js";
import { setBusy } from "./panels/copilot.js";
import { dispatchView } from "./panels/center.js";
import { recordDecision } from "./core/decisions.js";

// Build the "How I understood this" reasoning trace from a manipulation response.
// Shows the 3-layer pipeline at work (understand → choose → validate) using the
// REAL fields the backend returns — nothing fabricated. Returns null if there's
// no reasoning to show, so plain messages are unaffected.
function _reasoningMeta(res) {
  if (!res || (!res.detected_intent && !res.selected_operation)) return null;
  const layerName = {
    direct: "Direct command",
    intent: "Intent understanding",
    unrecognized: "Not recognized",
  }[res.understanding_layer] || (res.understanding_layer || "Reasoning");
  const sourceName = {
    llm: "AI language model",
    keyword: "keyword match",
    character: "design-character classifier",
  }[res.intent_source] || res.intent_source;
  // Structured geometry-validation verdict from the backend self-debug loop
  // (validate_design + design_debug). Surfaced as the "Validated" step's detail.
  const vr = res.validation_report || null;
  const checks = vr && vr.checks
    ? Object.entries(vr.checks)
        .filter(([, c]) => c && !c.skipped)
        .map(([name, c]) => ({ name, passed: !!c.passed, message: c.message || "" }))
    : [];
  return {
    kind: "reasoning",
    layer: layerName,
    intent: res.intent_label || res.detected_intent || "—",
    source: sourceName,
    operation: res.selected_operation || "—",
    validation: res.validation || (res.geometry_changed ? "passed" : "—"),
    changed: !!res.geometry_changed,
    why: res.reason || res.message || "",
    // real validation detail (empty when there was no site to validate against)
    validationReport: vr,
    checks,
    selfDebug: Array.isArray(res.self_debug_log) ? res.self_debug_log : [],
  };
}

// Parse a free-form manipulation amount typed by the user, scoped to the armed
// pendingTool. Returns a transform payload {dx,dy} | {rotation} | {scale} or null.
const _DIRS = {
  north: [0, 1], n: [0, 1], up: [0, 1], south: [0, -1], s: [0, -1], down: [0, -1],
  east: [1, 0], e: [1, 0], right: [1, 0], west: [-1, 0], w: [-1, 0], left: [-1, 0],
  northeast: [0.707, 0.707], ne: [0.707, 0.707], northwest: [-0.707, 0.707], nw: [-0.707, 0.707],
  southeast: [0.707, -0.707], se: [0.707, -0.707], southwest: [-0.707, -0.707], sw: [-0.707, -0.707],
};
function _parseManip(tool, text) {
  const low = (text || "").toLowerCase();
  if (tool === "move") {
    const d = low.match(/(\d+(?:\.\d+)?)/);
    const dist = d ? parseFloat(d[1]) : null;
    let dir = null;
    // Match the longest direction word first (so "northeast" wins over "north").
    // NOTE: build the word-boundary regex from a RegExp LITERAL fragment — a
    // string like "\\b" becomes a backspace char inside new RegExp(), which
    // silently never matches (this was the Move bug).
    const words = Object.keys(_DIRS).sort((a, b) => b.length - a.length);
    for (const w of words) {
      const re = new RegExp("(?:^|[^a-z])" + w + "(?![a-z])");
      if (re.test(low)) { dir = _DIRS[w]; break; }
    }
    if (dist == null || !dir) return null;
    return { dx: +(dir[0] * dist).toFixed(3), dy: +(dir[1] * dist).toFixed(3) };
  }
  if (tool === "rotate") {
    const m = low.match(/(-?\d+(?:\.\d+)?)/);
    if (!m) return null;
    let a = parseFloat(m[1]);
    if (/clockwise/.test(low) && !/counter|anti/.test(low)) a = -Math.abs(a);
    else if (/counter|anti/.test(low)) a = Math.abs(a);
    return { rotation: +a.toFixed(3) };
  }
  if (tool === "scale" || tool === "pushpull") {
    const pct = low.match(/(\d+(?:\.\d+)?)\s*%/);
    if (pct) {
      const f = parseFloat(pct[1]) / 100;
      const shrink = /(shrink|reduce|smaller|down|pull)/.test(low);
      return { scale: +(shrink ? 1 - f : 1 + f).toFixed(3) };
    }
    const x = low.match(/(\d+(?:\.\d+)?)\s*x/) || low.match(/(\d+(?:\.\d+)?)/);
    if (x) return { scale: +parseFloat(x[1]).toFixed(3) };
  }
  return null;
}

// Detect a full manipulation command from free text (kind + target part), e.g.
// "move left wing 3m east", "rotate building 15 degrees", "scale 1.2".
function _parseFreeManip(text) {
  const low = (text || "").toLowerCase();
  let kind = null;
  if (/\b(move|shift|nudge|translate)\b/.test(low)) kind = "move";
  else if (/\b(rotate|turn|spin)\b/.test(low)) kind = "rotate";
  else if (/\b(scale|resize|grow|shrink|enlarge)\b/.test(low)) kind = "scale";
  if (!kind) return null;
  const transform = _parseManip(kind, low);
  if (!transform) return null;
  // Target part: "left wing" / "right wing" / "base" → wing; else whole building.
  let partId = "building", partLabel = "building";
  const wingMatch = low.match(/\b(base|left|right|main|front|back|north|south|east|west)\s+(?:wing|arm)\b/);
  if (wingMatch || /\bwing\b/.test(low)) {
    const role = wingMatch ? wingMatch[1] : null;
    const wings = (getState().buildings?.[0]?.wings) || [];
    const match = role ? wings.find((w) => (w.role || "").toLowerCase().includes(role)) : wings[0];
    if (match) {
      const idx = match.wing_index ?? match.index ?? 0;
      partId = `wing_${idx}`; partLabel = `${match.role || "wing"} wing`;
    }
  }
  return { kind, transform, partId, partLabel };
}

async function _applyFreeManip(message, cmd) {
  pushMessage("user", message);
  setState({ selectedPartId: cmd.partId, selectedPartLabel: cmd.partLabel });
  const { transformSelectedBuilding } = await import("./agentClient.js");
  const res = await transformSelectedBuilding(cmd.transform);
  _recordManip(cmd.kind, cmd.transform, res);
  if (res && res.rejected) {
    pushMessage("assistant", `🚫 ${res.reason || "Rejected."}${res.suggestion ? `\n💡 ${res.suggestion}` : ""}`, _manipChips());
  } else if (res) {
    pushMessage("assistant", `✅ ${cmd.kind} applied to the ${cmd.partLabel}. Keep adjusting:`, _manipChips());
    setState({ centerView: "viewer" });
  } else {
    pushMessage("assistant", "Couldn't apply that — make sure a building is generated.");
  }
}

function _detectManipulation(text) {
  const low = (text || "").toLowerCase();

  // Corner placement: "place towards the northeast corner", "move to the top-left
  // corner". Routed to the feedback layer (backend place_corner snaps the building
  // to that site corner). Checked FIRST so "corner" isn't read as a generic move.
  if (low.includes("corner")) {
    return { kind: "feedback" };
  }
  // Edge placement: "place against the north edge", "hug the west side". Routed to
  // feedback (place_edge). Excludes floor moves ("move bottom floors ... edge").
  if (/\b(edge|side|wall)\b/.test(low) && /\b(north|south|east|west|top|bottom|left|right)\b/.test(low)
      && /\b(place|move|put|shift|push|hug|against|along|near)\b/.test(low) && !/\bfloor/.test(low)) {
    return { kind: "feedback" };
  }

  // Move detection: "move 5m north", "shift 10 east", etc.
  const moveMatch = low.match(/(?:move|shift|nudge|translate)\s+(\d+(?:\.\d+)?)\s*m(?:eters?)?\s+(north|south|east|west|up|down|left|right|n|s|e|w|northeast|northwest|southeast|southwest|ne|nw|se|sw)/);
  if (moveMatch) {
    const dist = parseFloat(moveMatch[1]);
    const dir = moveMatch[2].toLowerCase();
    const dirs = {
      "north": [0, 1], "n": [0, 1], "up": [0, 1],
      "south": [0, -1], "s": [0, -1], "down": [0, -1],
      "east": [1, 0], "e": [1, 0], "right": [1, 0],
      "west": [-1, 0], "w": [-1, 0], "left": [-1, 0],
      "northeast": [0.707, 0.707], "ne": [0.707, 0.707],
      "northwest": [-0.707, 0.707], "nw": [-0.707, 0.707],
      "southeast": [0.707, -0.707], "se": [0.707, -0.707],
      "southwest": [-0.707, -0.707], "sw": [-0.707, -0.707],
    };
    const [dx, dy] = dirs[dir] || [0, 0];
    return { kind: "move", dx: dx * dist, dy: dy * dist };
  }

  // Rotate detection: "rotate 30 degrees", "turn 45 clockwise", etc.
  const rotateMatch = low.match(/(?:rotate|turn|spin)\s+(\d+(?:\.\d+)?)\s*(?:degrees?)?\s*(clockwise|counter|anti|ccw|cw)?/);
  if (rotateMatch) {
    let angle = parseFloat(rotateMatch[1]);
    const dir = rotateMatch[2];
    if (dir && (/counter|anti|ccw/.test(dir))) angle = Math.abs(angle);
    else if (dir && (/clockwise|cw/.test(dir))) angle = -Math.abs(angle);
    return { kind: "rotate", rotation: angle };
  }

  // Natural-language scale (no number): "make it bigger", "building is too small",
  // "scale up the building", "increase the massing size". Maps to a sensible scale
  // factor and routes to the Scale tool — these used to fall through to the agent
  // chat and fail with "Failed to fetch". A percentage, if present, refines it.
  const wantsBigger = /\b(bigger|larger|too small|very small|increase (the )?(size|mass|massing|footprint|scale)|scale up|grow|enlarge|expand|more (mass|massing|area))\b/.test(low);
  const wantsSmaller = /\b(smaller|too (large|big)|reduce (the )?(size|mass|massing|footprint|scale)|scale down|shrink|less (mass|massing))\b/.test(low);
  if ((wantsBigger || wantsSmaller) && !/\bfloors?\b|\bcorner\b|\bwing\b/.test(low)) {
    const pct = low.match(/(\d+(?:\.\d+)?)\s*%/);
    let factor;
    if (pct) {
      const f = parseFloat(pct[1]) / 100;
      factor = wantsSmaller ? 1 - f : 1 + f;
    } else {
      // Defaults per spec: "scale up" 1.25, generic bigger/small 1.2; smaller 0.8.
      factor = wantsSmaller ? 0.8 : (/\bscale up\b/.test(low) ? 1.25 : 1.2);
    }
    return { kind: "scale", scale: +factor.toFixed(3) };
  }

  // Scale detection: "scale 1.2", "scale 20% bigger", "shrink 10%", etc.
  const scaleMatch = low.match(/(?:scale|resize|grow|shrink|enlarge|reduce)\s+(\d+(?:\.\d+)?)\s*(%|x)?/);
  if (scaleMatch) {
    let factor = parseFloat(scaleMatch[1]);
    const unit = scaleMatch[2];
    const isShrink = /shrink|reduce|smaller|down|pull/.test(low);
    if (unit === "%") factor = (isShrink ? 1 - factor : 1 + factor) / 100;
    if (isShrink && !unit) factor = 1 - (factor - 1);
    return { kind: "scale", scale: factor };
  }

  // Per-wing floors: "add 2 floors on the right wing" — must be checked BEFORE the
  // generic floors pattern so the wing isn't lost. Routed to the feedback layer.
  const wingFloorMatch = low.match(/(add|remove)\s+(\d+)\s*(?:floors?|stor(?:eys?|ies)|levels?)\s+(?:on|to|onto|in)\s+(?:the\s+)?(right|left|north|south|east|west|main|front|back)\s+wing/);
  if (wingFloorMatch) {
    return { kind: "feedback" };  // hand the raw text to the AI feedback layer
  }

  // Floor-level move: "move bottom 5 floors close to north edge", "move top 2 floors
  // front by 3m" — any move/shift that mentions floors + a direction goes to feedback.
  if (/\b(move|shift|slide|push|pull)\b/.test(low) && /\bfloors?\b/.test(low)
      && /\b(north|south|east|west|northeast|northwest|southeast|southwest|front|back|forward|backward|left|right|toward|towards|close to|near)\b/.test(low)) {
    return { kind: "feedback" };
  }

  // Facade alignment / orientation: "align long facade to north", "make the long
  // facade face the top", "face the building toward the park", "orient to south".
  // These are rotations to face a direction — handled by the feedback/reason layer.
  if (/\b(align|face|facing|orient|orientation|rotate to face)\b/.test(low)
      && /\b(facade|frontage|front|long side|building|mass|street|north|south|east|west|top|bottom|left|right|park|road|edge)\b/.test(low)) {
    return { kind: "feedback" };
  }

  // Absolute floor count: "make it 10 floors", "set to 20 floors", "20 floors".
  // Routed to feedback (the backend set_floors op resolves it against the current
  // count and rebuilds the plate stack).
  if (/(?:make it|set(?:\s+it)?(?:\s+to)?|change to|i want|build)\s+(?:.*?\b)?\d+\s*(?:floors?|stor(?:eys?|ies)|levels?)/.test(low)
      || /^\s*\d+\s*(?:floors?|stor(?:eys?|ies)|levels?)\s*$/.test(low)) {
    return { kind: "feedback" };
  }

  // Relative floors add/remove: "add 2 floors", "remove 3 storeys". Routed to the
  // feedback layer too — that's where the plate-stack rebuild lives (a plain
  // move/rotate/scale transform ignores floors entirely).
  if (/(?:add|plus|\+|remove|minus)\s*\d+\s*(?:floors?|stor(?:eys?|ies)|levels?)/.test(low)) {
    return { kind: "feedback" };
  }

  // Set a metre height: "set to 45m", "make it 60 meters" — also feedback.
  if (/(?:set to|make it|height)\s+\d+(?:\.\d+)?\s*m(?:eters?)?/.test(low)) {
    return { kind: "feedback" };
  }

  return null;
}

async function _tryApplyManipulation(message) {
  // Only apply if a building is generated
  if (!(getState().buildings || []).length) return false;

  const cmd = _detectManipulation(message);
  if (!cmd) return false;

  // Floor-level commands (per-wing floors, floor-range moves, absolute floor counts)
  // are handled by the architectural-feedback layer, which has the floor-plate ops
  // (set_floors / floor_add_wing / floor_move). Hand the raw text straight to it.
  if (cmd.kind === "feedback") {
    await _applyArchitecturalFeedback(message);
    return true;
  }

  pushMessage("user", message);
  const { transformSelectedBuilding } = await import("./agentClient.js");
  const res = await transformSelectedBuilding(cmd);
  _recordManip(cmd.kind, cmd, res);

  if (res && res.rejected) {
    // FAILED — show the real reason + suggestion (Fix 1: never claim success).
    const reason = res.reason || "the change would leave the site boundary";
    const suggestion = res.suggestion || "a smaller amount";
    pushMessage("assistant", `Action failed: ${reason}. Try ${suggestion}.`);
  } else if (res && !res.rejected) {
    // SUCCESS — update the viewer and offer to save/optimize this edited version.
    const verb = cmd.kind === "scale" ? (cmd.scale >= 1 ? "Scaled up" : "Scaled down") : "Updated";
    setState({ centerView: "viewer", lastManipulationPrompt: message });
    pushMessage(
      "assistant",
      `✅ ${verb} the building. Save this version, keep editing, or optimize it now?`,
      [
        { label: "Save as New Shape Option", intent: "save_option", primary: true },
        { label: "Optimize this version", message: "optimize", intent: "optimize", optimizeScope: "current" },
        { label: "Continue Editing", intent: "continue_editing" },
        { label: "Discard Changes", intent: "discard_changes" },
      ]
    );
  } else {
    // res === null → the request itself errored (network/backend).
    pushMessage("assistant", "⚠️ Couldn't reach the backend to apply that change. Make sure the server is running, then try again.");
  }
  return true;
}

// ---------------------------------------------------------------------------
// Workflow navigation — recognize "advance the workflow" phrases and move the
// user to the next stage (or tell them what's next), instead of the agent SSE
// fallback that only says "I finished that step."
// ---------------------------------------------------------------------------
const _NAV_PATTERNS = [
  /^\s*(next( step)?|continue|proceed|go on|move on|carry on|what(\s|')?s next|what now|next\??)\s*[.!?]?\s*$/i,
  /^\s*(done|finished|i finished|ok(ay)?|ready|let'?s go|go ahead|i'?m done)\s*[.!?]?\s*$/i,
  /\b(what should i do next|where to next|whats? the next step|how do i proceed)\b/i,
];
function _looksLikeNavigation(text) {
  const low = (text || "").trim().toLowerCase();
  if (!low) return false;
  return _NAV_PATTERNS.some((re) => re.test(low));
}

async function _handleNavigation(message) {
  pushMessage("user", message);
  const s = getState();
  const { WORKFLOW, nextPromptFor, tryAdvance, enterStage } = await import("./core/workflow.js");
  const def = WORKFLOW[s.stage];

  // If the current stage isn't finished yet, tell the user what's still needed
  // here rather than skipping ahead.
  if (def && typeof def.isComplete === "function" && !def.isComplete(s)) {
    const { text, actions } = nextPromptFor(s.stage);
    pushMessage(
      "assistant",
      text || "Finish the current step first — then say *'next'* to continue.",
      actions || []
    );
    return;
  }

  // Stage complete (or no completion gate) → advance to the NEXT stage that isn't
  // already finished. This skips stages the user has effectively completed (e.g.
  // after running optimization at SHAPE_EDIT, "next" jumps past OPTIMIZE to COMPARE
  // instead of re-opening the optimizer).
  let target = def && def.next;
  let hops = 0;
  while (target && hops < 6) {
    const tdef = WORKFLOW[target];
    if (!tdef) break;
    // Stop at the first stage that the user can enter AND hasn't already completed.
    const enterable = tdef.canEnter(getState());
    const finished = typeof tdef.isComplete === "function" && tdef.isComplete(getState());
    if (enterable && !finished) break;
    if (!enterable) break;          // blocked → land here so tryAdvance explains why
    target = tdef.next;             // already finished → skip to the next
    hops += 1;
  }

  if (target) {
    const moved = tryAdvance(target, { announce: true });
    if (!moved) return; // tryAdvance already explained why it's blocked.
    return;
  }

  // No next stage (end of workflow) — re-announce the current stage's guidance.
  const { text, actions } = nextPromptFor(s.stage);
  pushMessage("assistant", text || "You're at the final step. You can export the project.", actions || []);
  if (!text) enterStage(s.stage, { announce: false });
}

// ---------------------------------------------------------------------------
// Architectural-feedback mode — natural-language design intent. Detect critique-
// style phrasing (NOT an explicit move/rotate/scale amount) so we can route it to
// the AI reasoning layer instead of the literal command parser.
// ---------------------------------------------------------------------------
const _FEEDBACK_PATTERNS = [
  /\bdaylight|sunlight|more (light|sun)|brighter\b/,
  /\b(too )?(compact|cramped|dense|crowded|tight|bulky|heavy|massive)\b/,
  /\b(taller|make it tall|more floors|more capacity|keep this option)\b/,
  // courtyard + common misspellings (courdyard/courtyrd/coutyard/cordyard/atrium/void)
  /cou?r?[td]y?ard|courtyrd|atrium|central void|\bvoid\b/,
  /\b(open space|more open|spacious|breathing room|airy|lighter)\b/,
  /\bstreet presence|overshadow|shadow on|privacy|views? (toward|to)\b/,
  /\bfeels?\b.*\b(too|more|less)\b/,
  /\bi want\b/,
  // Architectural CHARACTER / identity language.
  /\b(residential|commercial|corporate|office|iconic|landmark|elegant|premium|luxur|sculptural|monumental|institutional|boxy|generic|memorable|refined|warmer|inviting|welcoming|human|character|identity|presence)\b/,
  // FACADE / frontage articulation language.
  /\b(facade|frontage|articulat|recess|projection|balcon|terrac|rhythm|flat|frontage|street edge)\b/,
  // TOWER / wing / proportion language.
  /\b(tower|wing|podium|slender|slimmer|wider|stretch|compress|taper|twist|separation|proportions?|silhouette|massing)\b/,
  // Slider/critique verbs architects use.
  /\b(make it (more|less)|give it|too (rigid|aggressive|engineered|repetitive)|open it up|loosen|stand out|breathing)\b/,
];

function _looksLikeFeedback(text) {
  const low = (text || "").toLowerCase();
  // An explicit amount ("5m", "30 degrees", "1.2x", "scale", "rotate") is a manual
  // command — let the literal parser handle it, not the reasoning layer.
  if (/\b(move|rotate|scale|stretch|push|pull)\b/.test(low) && /\d/.test(low)) return false;
  return _FEEDBACK_PATTERNS.some((re) => re.test(low));
}

// Broad gate: is this typed text a building CHANGE the user wants applied (vs a
// question, navigation, or generation request)? Permissive on purpose — once a
// shape is being edited, almost any design verb/noun should reach the manipulation
// backend, which decides what to do (and honestly fails on gibberish). We exclude
// only obvious questions (handled by the QA layer earlier) and empty text.
const _MANIP_VERB_RX =
  /\b(move|shift|relocat|reposition|place|put|rotate|turn|spin|scale|resize|grow|shrink|enlarge|reduce|increase|decrease|extend|lengthen|shorten|stretch|compress|expand|add|remove|raise|lower|make|set|give|open|close|carve|create|cut|orient|align|face|push|pull|widen|narrow|taper|twist|tilt|flip|center|centre|pull back|set back|step back)\b/;
const _DESIGN_NOUN_RX =
  /\b(facade|frontage|footprint|foot print|floor|storey|story|height|tall|courtyard|atrium|void|wing|tower|podium|mass|massing|edge|corner|setback|noise|daylight|sun|light|view|park|road|street|metro|transit|plaza|frontage|depth|width|orientation|building|shape|site|centre|center|north|south|east|west)\b/;
function _isLikelyManipulation(text) {
  const low = (text || "").trim().toLowerCase();
  if (!low) return false;
  // Pure questions are handled by the QA layer before this; don't manipulate on a
  // leading question word with no imperative verb.
  if (/^(what|why|how|did|does|is|are|can|will|should|where|when)\b/.test(low) && !_MANIP_VERB_RX.test(low)) {
    return false;
  }
  return _MANIP_VERB_RX.test(low) || _DESIGN_NOUN_RX.test(low) || _looksLikeFeedback(low);
}

async function _applyArchitecturalFeedback(message) {
  pushMessage("user", message);

  // Pre-apply summary (spec #5): Target / Operation / Value, so the user sees what
  // the selected part will receive before it happens.
  const targetName = getState().selectedPartLabel || "the whole building";
  const floorM = message.match(/(?:add|plus|\+)\s*(\d+)\s*(?:floors?|stor(?:eys?|ies)|levels?)/i);
  if (floorM) {
    pushMessage("assistant", `**Target:** ${targetName}\n**Operation:** Add Floors\n**Value:** +${floorM[1]}`);
  }

  setBusy(true);
  setStatus("Reasoning about the design…");
  try {
    const { applyArchitecturalFeedback } = await import("./agentClient.js");
    const res = await applyArchitecturalFeedback(message);
    if (!res) {
      pushMessage("assistant", "Couldn't interpret that — generate a building first.");
      return;
    }
    // Keep the full reasoning/actions trace in the DECISION GRAPH (its own panel),
    // not the chat. The chat just confirms the outcome in one short line.
    recordDecision("editing", "architectural_feedback", {
      input: message,
      result: res.reason || "Architectural feedback applied",
      data: {
        reason: res.reason,
        source: res.reasoning_source,
        observations: res.observations || [],
        actions: (res.actions || []).map((a) => ({ text: a.text, op: a.op, accepted: a.accepted })),
        floors: res.floors, height_m: res.height_m,
      },
    });

    // Use the backend STATUS envelope (Fix 1/2): geometry_changed is the source of
    // truth. NEVER say "Updated building" unless the geometry actually changed.
    const partName = res.selected_part_name || getState().selectedPartLabel || "the building";
    const changed = res.geometry_changed ?? res.applied;

    if (res.target_mismatch) {
      pushMessage(
        "assistant",
        `⚠️ Manipulation target mismatch: you selected **${partName}**, but the change landed on **${res.modified_part || "another element"}**. Please re-select the part and try again.`
      );
      setState({ centerView: "viewer" });
    } else if (changed && res.status !== "failed") {
      // SUCCESS — RE-RENDER the 3D viewer with the moved/edited geometry, THEN offer to
      // save/optimize. Without the re-render the backend moved the building but the
      // viewport kept showing the old position — "Updated" with no visible movement.
      setState({ centerView: "viewer", lastManipulationPrompt: message });
      try {
        const { refreshExplorer, forceViewerRerender } = await import("./agentClient.js");
        await refreshExplorer();                 // pull the new geometry into s.buildings
        await forceViewerRerender({ flash: true }); // redraw + glow the change
      } catch (e) { console.error("[copilot] re-render after manipulation failed", e); }
      pushMessage(
        "assistant",
        `✅ Updated **${partName}**. Save this version, keep editing, or optimize it now?`,
        [
          { label: "Save as New Shape Option", intent: "save_option", primary: true },
          { label: "Optimize this version", message: "optimize", intent: "optimize", optimizeScope: "current" },
          { label: "Continue Editing", intent: "continue_editing" },
          { label: "Discard Changes", intent: "discard_changes" },
        ],
        _reasoningMeta(res),  // "How I understood this" panel data
      );
    } else if (res.status === "no_change") {
      // ALREADY OPTIMAL — a context placement ("move away from noise") resolved its
      // target but the building is already at the best spot, so nothing moved. This is
      // NOT a failure: say so honestly and positively, and DON'T offer Save/Optimize
      // (there's no new version to save). Previously this fell through to a fake
      // "✅ Updated" with buttons even though the building hadn't moved.
      const reason = res.reason || res.message || "the building is already in the best position for that.";
      pushMessage("assistant", `✅ No change needed — ${reason}`, [], _reasoningMeta(res));
    } else {
      // FAILED — show the exact reason + suggestion; do NOT claim success (Fix 1).
      const reason = res.reason || "the requested change could not be applied";
      const suggestion = res.suggestion || "try a smaller amount or a different command";
      pushMessage("assistant", `Action failed: ${reason}. Try ${suggestion}.`, [], _reasoningMeta(res));
    }
  } finally {
    setBusy(false);
    setStatus("Ready");
  }
}

// Record a manipulation into the decision timeline (accepted or rejected, with
// the part it targeted and the amount).
function _recordManip(tool, transform, res) {
  const part = getState().selectedPartLabel || "building";
  if (res && res.rejected) {
    recordDecision("editing", `${tool}_rejected`, {
      input: JSON.stringify(transform), result: res.reason || "Rejected (boundary violation)",
      data: { part, rejected: true, suggestion: res.suggestion },
    });
  } else if (res) {
    recordDecision("editing", `${tool}_applied`, {
      input: JSON.stringify(transform), result: `${tool} applied to ${part}`,
      data: { part, transform },
    });
  }
}

// Quick-reply chips: core actions only (no manipulation buttons - use text prompts instead)
function _manipChips() {
  return [
    { label: "AI Feedback", message: "Give architectural feedback", intent: "feedback" },
    { label: "Optimize", message: "Optimize the building placement", intent: "optimize" },
    { label: "Compare", message: "compare", intent: "compare" },
  ];
}

function closeRing(points) {
  const ring = points.map((p) => [Number(p[0]), Number(p[1])]);
  if (
    ring.length &&
    (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1])
  ) {
    ring.push([ring[0][0], ring[0][1]]);
  }
  return ring;
}

// The map draws the boundary in geographic degrees ([lng, lat]), but the agent's
// geometry engine works entirely in METERS (building footprints, setbacks of "3.0",
// site-fit checks). Sending raw degrees makes the site span ~0.0006° which the agent
// reads as ~0 m² — so nothing fits and no building is generated. Project the ring to
// a local metric frame (equirectangular about its centroid; sub-meter accurate at
// site scale) before it goes to the backend. The origin is returned so the result
// could be unprojected back to lng/lat if ever needed.
function projectRingToMeters(ring) {
  if (!ring || ring.length < 3) return { ring, origin: null };
  const lngs = ring.map((p) => Number(p[0]));
  const lats = ring.map((p) => Number(p[1]));
  const lng0 = lngs.reduce((a, b) => a + b, 0) / lngs.length;
  const lat0 = lats.reduce((a, b) => a + b, 0) / lats.length;
  const R = 6378137; // WGS84 equatorial radius (m)
  const cosLat = Math.cos((lat0 * Math.PI) / 180);
  const projected = ring.map((p) => [
    ((Number(p[0]) - lng0) * Math.PI) / 180 * R * cosLat,
    ((Number(p[1]) - lat0) * Math.PI) / 180 * R,
  ]);
  return { ring: projected, origin: { lng: lng0, lat: lat0 } };
}

// ---------------------------------------------------------------------------
// Coordinate / location parsing for the SITE stage (frontend-owned).
// ---------------------------------------------------------------------------
function parseCoords(text) {
  const m = /(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)/.exec(text || "");
  if (!m) return null;
  const lat = Number(m[1]);
  const lng = Number(m[2]);
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  return { lat, lng };
}

// Resolve a free-text location to coordinates using the REAL backend geocoder,
// falling back to the browser's geocoder shim only if the backend is unreachable.
async function resolveLocation(text) {
  const coords = parseCoords(text);
  if (coords) return { name: text, ...coords };
  try {
    const { results } = await api.agent.geocode(text, 1);
    if (results && results.length) {
      const r = results[0];
      return { name: r.name || text, lat: r.lat, lng: r.lng };
    }
  } catch (err) {
    // Backend geocoder down — surface it but let the caller fall back.
    pushError(`Backend geocoder unavailable: ${err.message}`);
  }
  return null;
}

// ---------------------------------------------------------------------------
// SITE stage handler — fly the map, drop a pin, advance to BOUNDARY.
// ---------------------------------------------------------------------------
async function handleSite(message) {
  setStatus("Locating site…");
  setState({ isLocatingSite: true });
  const loc = await resolveLocation(message);
  if (!loc) {
    setState({ isLocatingSite: false });
    pushMessage(
      "assistant",
      "I couldn't find that place. Try a place name (e.g. *Bangalore*), an " +
        "address, or coordinates like *12.9716, 77.5946*."
    );
    setStatus("Ready · Site");
    return;
  }
  await dispatchView({
    type: "map",
    payload: { action: "fly_to", site: { center: loc, location_name: loc.name } },
  });
  setState({
    stage: STAGES.BOUNDARY,
    centerView: "map",
    location: loc,
    locationSaved: true,
  });
  recordDecision("site", "location_selected", {
    input: loc.name, result: "Location confirmed",
    data: { lat: loc.lat, lng: loc.lng },
  });
  pushMessage(
    "assistant",
    `Located **${loc.name}**. Now outline the **site boundary** on the map — click ` +
      "to drop points, drag vertices to adjust, right-click a vertex to remove it. " +
      "When the polygon is closed, choose **Save Boundary**.",
    [
      { label: "Draw Boundary", message: "draw boundary", intent: "draw_boundary" },
    ]
  );
  setStatus("Ready · Boundary");
}

// ---------------------------------------------------------------------------
// BOUNDARY stage handler — analyze + persist the drawn boundary, then hand the
// design conversation to the agent backend.
// ---------------------------------------------------------------------------
async function handleBoundary(message, action) {
  const s = getState();
  const intent = action?.intent;

  if (intent === "draw_boundary" || /draw|edit/.test(message.toLowerCase())) {
    await dispatchView({ type: "map", payload: { action: "enable_draw" } });
    setState({ isBoundaryActivating: true });
    pushMessage("assistant", "Drawing enabled. Click on the map to outline the site.");
    return;
  }

  if (intent === "reset_boundary") {
    setState({ boundary: [], boundarySaved: false });
    await dispatchView({ type: "map", payload: { action: "enable_draw" } });
    pushMessage("assistant", "Boundary cleared. Outline a new one.");
    return;
  }

  // Save / confirm path.
  const drawn = s.boundary || [];
  if (drawn.length < 3) {
    pushMessage("assistant", "Outline at least three points before saving the boundary.");
    return;
  }

  setStatus("Analyzing boundary…");
  setState({ isAnalyzingBoundary: true });

  const geoRing = closeRing(drawn);
  // Project to a local metric frame so the agent (which works in meters) sees a
  // real-sized site instead of a ~0 m² patch of degrees. All backend calls below
  // use the metric ring so analysis, buildable zone and placement stay consistent.
  const { ring, origin } = projectRingToMeters(geoRing);

  // Persist the confirmed site as the shared single source of truth via the
  // runtime route (connection/notebook_logic/site_state). The agent, geometry,
  // optimization, and decision-graph runtimes all read this same confirmed site.
  try {
    await api.runtime.confirmSite(geoRing, {
      project: true,
      location_name: s.location?.name,
    });
  } catch (err) {
    pushError(`Could not save confirmed site: ${err.message}`);
  }

  let areaSqm = null;
  let buildable = null;
  try {
    // Real backend boundary analysis + buildable zone (agent tools).
    const analysis = await api.agent.analyzeBoundary(ring);
    areaSqm = analysis?.area_sqm ?? null;
    setState({ siteAnalysis: analysis?.analysis || null });
    const bz = await api.agent.buildableZone(ring, 3);
    buildable = bz?.buildable_boundary || null;
    setState({ buildableBoundary: buildable });
  } catch (err) {
    // Analysis is best-effort; a boundary can still be saved without it.
    pushError(`Boundary analysis unavailable: ${err.message}`);
  }

  // Create the agent session seeded with the confirmed site boundary so every
  // later agent turn already knows the site. (build_initial_state reads
  // layout_payload.site_boundary.)
  let sessionId = s.sessionId;
  try {
    const { ensureAgentAvailable, ensureSession } = await import("./agentClient.js");
    const ok = await ensureAgentAvailable();
    if (ok) {
      sessionId = await ensureSession({
        user_prompt: "",
        site_boundary: ring,
        workflow_mode: "full",
      });
      // Persist the confirmed boundary onto the session state as well. Record the
      // projection origin (lng/lat the metric frame is centered on) so the metric
      // geometry can be mapped back to the globe for export.
      await api.agent.saveSessionBoundary(sessionId, ring, {
        center: origin || (s.location ? { lat: s.location.lat, lng: s.location.lng } : undefined),
        location_name: s.location?.name,
      });
    }
  } catch (err) {
    pushError(`Could not start an agent session: ${err.message}`);
  }

  await dispatchView({
    type: "map",
    payload: {
      action: "boundary_saved",
      site: {
        confirmed_site_boundary: { type: "Polygon", coordinates: [ring] },
        site_area: areaSqm,
      },
    },
  });

  // Persist boundary state, then let the workflow controller advance to SHAPES
  // (sets centerView + emits the "describe what to generate" guiding prompt).
  setState({
    boundary: drawn,
    boundarySaved: true,
    isAnalyzingBoundary: false,
    // The 3D viewer draws s.site.boundary in the agent's METRIC coordinate space,
    // so feed it the projected ring (not the raw lng/lat).
    site: {
      ...(s.site || {}),
      boundary: ring.map((p) => [Number(p[0]), Number(p[1])]),
      site_area: areaSqm,
      buildable_boundary: buildable,
    },
  });

  const areaText = areaSqm ? ` (~${Math.round(areaSqm).toLocaleString()} m²)` : "";
  pushMessage("assistant", `✅ Site boundary saved${areaText}.`);
  recordDecision("boundary", "boundary_drawn", {
    input: `${drawn.length} points`, result: `Site boundary saved (${Math.round(areaSqm || 0)} m²)`,
    data: { area_sqm: areaSqm },
  });
  // Urban Context Analysis runs automatically next: boot.js installed a store
  // watcher (contextController.watchBoundary) that fires runContextAnalysis() the
  // moment `boundarySaved` becomes true — fetching the 2 km OSM context in the
  // browser, rendering the digital twin, posting the AI report + scores, and asking
  // the context-aware building question. We just leave boundarySaved set (above).
  setStatus("Ready · Context");
}

// ---------------------------------------------------------------------------
// Route a message to the agent backend (used after a shape is selected; the
// SHAPES stage routes generation prompts to the Shape Library instead).
// ---------------------------------------------------------------------------

async function handleAgent(message) {
  try {
    const { ensureAgentAvailable, streamChat } = await import("./agentClient.js");
    const ok = await ensureAgentAvailable();
    if (!ok) {
      pushMessage(
        "assistant",
        `⚠️ The agent backend isn't reachable at \`${api.agentBase || "same origin"}\`. ` +
          "Start it with `uvicorn connection.app:app --port 8001` (from team_04/PY) " +
          "and reload."
      );
      return;
    }

    // STAGE 1 enforcement: in the SHAPES stage, ANY design/generation prompt
    // produces the Shape Library (multiple typologies to choose from) — even when
    // a specific shape is named. Shape generation + selection must always happen
    // before optimization, so we never let a prompt place a single building and
    // skip ahead. Once a shape is selected (SHAPE_EDIT onward), chat flows to the
    // agent normally. This also fires from the CONTEXT stage: after the urban-
    // context analysis we keep the user on the Context twin and ask the building
    // question there, so answering it (here) is what generates shapes + advances.
    const stg = getState().stage;
    if ((stg === STAGES.SHAPES || stg === STAGES.CONTEXT) && getState().boundarySaved) {
      await _generateMultiTypology(message);
      return;
    }

    recordDecision("shape", "shape_prompt_submitted", { input: message, result: "Prompt sent to agent" });
    const beforeCount = (getState().buildings || []).length;
    await streamChat(message);
    // After the turn settles, switch the center to the viewer if buildings exist.
    const after = getState().buildings || [];
    if (after.length) {
      if (after.length > beforeCount) {
        const b = after[after.length - 1];
        recordDecision("shape", "shape_generated", {
          result: `${b.building_type || "building"} generated inside the site`,
          data: { building_type: b.building_type, height_m: b.height_m, wings: (b.wings || []).length },
        });
      }
      setState({ centerView: STAGE_VIEW[getState().stage] || "viewer" });
    }
  } catch (err) {
    const raw = err.message || "Agent chat failed.";
    pushError(raw);
    // "Failed to fetch" is the browser's opaque network error — translate it into
    // something actionable instead of showing the user a bare technical string.
    const friendly = /failed to fetch|networkerror|load failed/i.test(raw)
      ? "I couldn't reach the design backend for that request. Make sure the server is running (uvicorn connection.app:app --port 8001), then try again. For shape changes, you can also use direct commands like *'make it bigger'*, *'add courtyard'*, or *'move to the north corner'*."
      : raw;
    pushMessage("assistant", `⚠️ ${friendly}`);
  }
}

// STAGE 1 — Shape generation. Generate multiple massing typologies and present
// them in the SHAPE LIBRARY for the user to pick from. NO optimization runs here:
// the options land in the `shapeOptions` bucket and the stage stays on SHAPES.
// Optimization only runs later, on the ONE shape the user selects.
const _SHAPE_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

async function _generateMultiTypology(message) {
  const sid = getState().sessionId;
  if (!sid) { pushMessage("assistant", "Start a session by saving a boundary first."); return; }
  recordDecision("shape", "shape_options_requested", { input: message, result: "Generating shape options" });
  setBusy(true);
  setStatus("Generating shape options…");
  try {
    // Context-aware generation: a high transit/accessibility context nudges
    // coverage up so the shape options reflect the urban context (more density
    // where the city supports it). Scores come from the Context Analysis stage.
    const cScores = getState().contextScores || {};
    const densityBias = Math.max(
      cScores.transit >= 75 ? 0.2 : 0,
      cScores.accessibility >= 75 ? 0.15 : 0
    );
    const genOpts = {};
    if (densityBias) genOpts.coverage_ratio = Math.min(0.9, 0.35 + densityBias);
    const res = await api.agent.generateOptions(sid, message, genOpts);
    const opts = res.options || [];
    if (!opts.length) {
      pushMessage("assistant", "I couldn't fit any shapes on this site — try a larger boundary, or tell me a specific shape.");
      return;
    }
    // Keep the raw shape options (footprint/type/fit) for the Shape Library — NOT
    // mapped into the optimization `options` bucket. All shapes visible at once.
    const shapeOptions = opts.map((o) => ({
      option_id: o.option_id, shape_type: o.shape_type, footprint: o.footprint,
      boundary: o.footprint, height_m: o.height_m, floors: o.floors,
      rotation_degrees: o.rotation_degrees, score: o.score, rank: o.rank,
      far: o.far, site_coverage: o.site_coverage, footprint_area: o.footprint_area,
      validation_report: o.validation_report || {},
    }));
    setState({
      shapeOptions,
      shapesByType: res.shapes_by_type || {},
      visibleShapeIds: new Set(shapeOptions.map((o) => o.option_id)),
      selectedShapeId: shapeOptions[0]?.option_id || null,
      selectedShapeType: null, // not yet committed — gates OPTIMIZE
      stage: STAGES.SHAPES, centerView: "shapes",
    });
    const program = res.program || {};
    recordDecision("shape", "shape_options_generated", {
      result: `${opts.length} shape options generated`,
      data: { typologies: res.typologies, count: opts.length },
    });
    const useTxt = program.building_use ? `${program.building_use} ` : "";
    const flrTxt = program.floors ? `${program.floors}-floor ` : "";
    const labelList = shapeOptions
      .map((o, i) => `**Shape ${_SHAPE_LETTERS[i] || i + 1}** (${o.shape_type})`)
      .join(", ");
    let directiveNotes = [];
    try {
      const { designGuidance } = await import("./core/overpass.js");
      directiveNotes = designGuidance(getState().contextScores || {});
    } catch { /* context optional */ }
    const ctxNote = directiveNotes.length
      ? `\n\n_Context-aware:_ ${directiveNotes.join("; ")}.`
      : "";
    pushMessage(
      "assistant",
      `Here are **${opts.length} ${flrTxt}${useTxt}massing options** to explore — ${labelList}. ` +
        "They're all shown in the **Shape Library** and the 3D viewport, scaled to fit your site. " +
        "Toggle 👁 to preview each one, then **select** the shape you'd like to take forward. " +
        "_(Optimization runs after you choose.)_" + ctxNote,
      shapeOptions.slice(0, 4).map((o, i) => ({
        label: `Select Shape ${_SHAPE_LETTERS[i] || i + 1}`,
        intent: "select_shape", optionId: o.option_id,
      }))
    );
    // Pre-warm the 3D shape preview so a shape is ready to show the moment the user
    // toggles its eye (drawn in the backend metric frame the footprints use).
    try {
      const viewer = await import("./views/viewerView.js");
      viewer.renderShapePreview(shapeOptions);
    } catch { /* views mount on view switch */ }
  } catch (err) {
    pushError(`Shape generation failed: ${err.message}`);
  } finally {
    setBusy(false);
    setStatus("Ready");
  }
}

// STAGE 2 — Shape selection. Commit to ONE shape: promote it to the session's
// placed building (backend), record the decision, and advance to SHAPE_EDIT.
// This is the ONLY path that unlocks optimization.
export async function confirmShapeSelection(opt) {
  const sid = getState().sessionId;
  if (!sid || !opt) { pushMessage("assistant", "Generate shapes first, then pick one."); return; }
  const i = (getState().shapeOptions || []).findIndex((o) => o.option_id === opt.option_id);
  const label = `Shape ${_SHAPE_LETTERS[i] || (i + 1)}`;
  setBusy(true);
  setStatus("Selecting shape…");
  try {
    const res = await api.agent.selectShape(sid, opt.option_id);
    // Mark the committed shape and place it as the single building, then pull the
    // explorer so buildings[] reflects the selection for transform/optimize/feedback.
    // Clear any STALE optimization options / visibility / ghost state from a prior
    // run so the viewer shows ONLY the freshly selected shape (not leftover shapes).
    setState({
      selectedShapeType: res.shape_type || opt.shape_type,
      selectedBuildingId: res.building_id,
      selectedOptionId: null,
      options: [],                      // drop old optimization options
      optimizationResult: null,
      visibleOptionIds: new Set(),      // empty = nothing from old options shown
    });
    const { refreshExplorer } = await import("./agentClient.js");
    await refreshExplorer();
    recordDecision("shape", "shape_selected", {
      input: label, result: `${res.shape_type || opt.shape_type} selected`,
      data: { option_id: opt.option_id, shape_type: res.shape_type },
    });
    pushMessage("user", `Select ${label}`);
    const { enterStage } = await import("./core/workflow.js");
    enterStage(STAGES.SHAPE_EDIT, { announce: false });
    // Switch to the viewer, then explicitly redraw from ONLY the selected building.
    // resetForFreshBuilding() wipes the multi-shape preview state (lastOptions/
    // ghosts) so the overlapping Shape-Library previews don't linger; renderBuildings
    // then draws just the one placed building from the refreshed explorer state.
    setState({ centerView: "viewer" });
    try {
      const viewer = await import("./views/viewerView.js");
      viewer.resetForFreshBuilding();
      viewer.renderBuildings(getState());
    } catch { /* viewer mounts later — activate() will pick up state */ }
    pushMessage(
      "assistant",
      `Great — going with the **${res.shape_type || opt.shape_type}** (${label}). ` +
        "You can fine-tune it now by typing commands — e.g. *'move 5m north'*, *'rotate 30'*, *'add 2 floors'* — " +
        "or just tell me how it should feel (*'more daylight'*, *'a larger courtyard'*). " +
        "When you're ready, type *'optimize'* to generate ranked design alternatives."
    );
  } catch (err) {
    pushError(`Could not select that shape: ${err.message}`);
  } finally {
    setBusy(false);
    setStatus("Ready");
  }
}

// ---------------------------------------------------------------------------
// Public entry — called by the copilot panel for every send.
// ---------------------------------------------------------------------------
function _annotateWithEdgeContext(message) {
  const edge = getState().selectedEdge;
  if (!edge) return message;
  // Prepend selected edge information to the message context
  const edgeInfo = `[Context: Selected edge is the **${edge.label}** (${edge.direction}). ` +
    `Nearest features: ${Object.entries(edge.nearest || {}).slice(0, 3).map(([k, v]) => `${k} ${v}m`).join(", ") || "none"}]`;
  return `${edgeInfo}\n\n${message}`;
}

export async function sendMessage(message, action = null) {
  // Client-only actions (e.g. trigger a download) run their handler and stop.
  if (action?.local && typeof action.handler === "function") {
    await action.handler();
    return;
  }

  // QUESTION-ANSWERING MODE. A typed question ("Did you move the building away
  // from noise?", "why did it rotate?", "what was the last action?") is answered
  // DIRECTLY from real app state — never routed to the agent SSE that only says
  // "I finished that step." Only fires for free-typed text (no chip action) and
  // not while AI-feedback mode is armed (that text is design intent). Returns null
  // for commands/critique, so geometry edits still flow to the normal routing.
  if (!action && !getState().pendingFeedback) {
    try {
      const { classifyMessage, tryAnswer } = await import("./core/copilotQA.js");
      if (classifyMessage(message)) {
        const answer = tryAnswer(message);
        if (answer) {
          pushMessage("user", message);
          pushMessage("assistant", answer);
          return;
        }
      }
    } catch (err) {
      console.warn("[copilot] QA layer error", err);
      // fall through to normal routing on any QA failure
    }
  }

  // Annotate message with selected edge context (will be included in feedback)
  const annotatedMessage = _annotateWithEdgeContext(message);

  // "AI Feedback" mode is armed (chip clicked) — the next typed message is design
  // intent for the reasoning layer, not a literal command. Disarm after handling.
  if (!action && getState().pendingFeedback) {
    setState({ pendingFeedback: false });
    await _applyArchitecturalFeedback(annotatedMessage);
    return;
  }

  // Shape selection (Stage 2) — a "Select Shape X" chip from the Shape Library.
  if (action?.intent === "select_shape") {
    const opt = (getState().shapeOptions || []).find((o) => o.option_id === action.optionId);
    if (!opt) { pushMessage("assistant", "That shape is no longer available — generate shapes again."); return; }
    await confirmShapeSelection(opt);
    return;
  }

  // Save the manipulated geometry as a NEW Shape Library version (Fix 3/4). Never
  // overwrites — the backend assigns a new shape_option_id with a parent pointer.
  if (action?.intent === "save_option") {
    const sid = getState().sessionId;
    if (!sid) { pushMessage("assistant", "No active session to save into."); return; }
    pushMessage("user", "Save as new shape option");
    setBusy(true);
    try {
      const prompt = getState().lastManipulationPrompt || null;
      const res = await api.agent.saveDesignOption(sid, { prompt });
      const oid = res?.shape_option_id || "option";
      recordDecision("editing", "saved_option", { input: prompt || "", result: `Saved ${oid}` });
      pushMessage(
        "assistant",
        `💾 Saved as **${oid}** in the Shape Library (${res?.total_saved || 1} saved version${(res?.total_saved || 1) > 1 ? "s" : ""}). ` +
          "Keep editing, or when you're ready type *'optimize'* — I'll ask whether to optimize the current shape or all saved shapes.",
        _manipChips()
      );
      // Refresh the explorer so the new version appears under the Shape Library.
      try { const { refreshExplorer } = await import("./agentClient.js"); await refreshExplorer(); } catch { /* optional */ }
    } catch (err) {
      pushMessage("assistant", `⚠️ Couldn't save that option: ${err.message}`);
    } finally {
      setBusy(false);
    }
    return;
  }
  if (action?.intent === "continue_editing") {
    pushMessage("user", "Continue editing");
    pushMessage("assistant", "Keep going — tell me the next change (e.g. *'add a courtyard'*, *'make it taller'*, *'move to the north corner'*).", _manipChips());
    return;
  }
  if (action?.intent === "discard_changes") {
    // Re-select the last SAVED version (or re-render the current building) so the
    // unsaved edit is visually dropped. Geometry already persisted is untouched.
    pushMessage("user", "Discard changes");
    pushMessage("assistant", "Discarded the unsaved change. The building is back to its last state.", _manipChips());
    try {
      const { forceViewerRerender } = await import("./agentClient.js");
      await forceViewerRerender();
    } catch { /* viewer optional */ }
    return;
  }

  // Part selection (spec #1/#2): a part chip ("Central Mass", "Right Wing") sets the
  // active manipulation target. Subsequent commands ("add 5 floors") modify ONLY this
  // part. Stored as selectedPartId + selectedPartLabel; sent on every manipulation.
  if (action?.intent === "select_part") {
    const partId = action.partId || "building";
    const partLabel = action.partLabel || "the whole building";
    setState({ selectedPartId: partId, selectedPartLabel: partLabel });
    recordDecision("editing", "part_selected", { input: partLabel, result: `Target set: ${partLabel}` });
    pushMessage("user", `Select ${partLabel}`);
    pushMessage(
      "assistant",
      `🎯 Target set: **${partLabel}**. Commands now affect only this part — e.g. *'add 5 floors'*, *'make it taller'*. Say *'select whole building'* to target everything.`
    );
    return;
  }
  // "select whole building" / "deselect" — clear the part target.
  if (!action && /^\s*(select (the )?whole building|deselect|clear selection|target (the )?whole building)\s*$/i.test(message)) {
    setState({ selectedPartId: "building", selectedPartLabel: "the whole building" });
    pushMessage("user", message);
    pushMessage("assistant", "🎯 Target set: **the whole building**. Commands now affect the entire massing.");
    return;
  }

  // "AI Feedback" chip — arm feedback mode and prompt for the design intent.
  if (action?.intent === "feedback") {
    if (!(getState().buildings || []).length) {
      pushMessage("assistant", "Generate a building first, then tell me how it should feel.");
      return;
    }
    setState({ pendingFeedback: true });
    pushMessage("user", "Give architectural feedback");
    pushMessage(
      "assistant",
      "**Architectural feedback** — tell me how the design should *feel* and I'll work out the moves. " +
        "Try *'I want more daylight'*, *'it feels too compact'*, or *'keep this option but make it taller'*.",
      [
        { label: "More daylight", message: "I want more daylight" },
        { label: "Feels too compact", message: "It feels too compact" },
        { label: "Make it taller", message: "Keep this option but make it taller" },
      ]
    );
    return;
  }

  // Detect manipulation commands directly from text (no button system)
  // Supports: "move 5m north", "rotate 30 degrees", "scale 1.2", "add 2 floors"
  if (!action && !getState().pendingFeedback) {
    const handled = await _tryApplyManipulation(message);
    if (handled) return;
    // not a manipulation command → fall through
  }

  // Workflow navigation — "next step", "done", "what now", "continue", "proceed".
  // These are NOT design commands; the user wants to advance the workflow. Move to
  // (or describe) the next stage using the WORKFLOW map instead of falling through
  // to the agent SSE, which only ever says "I finished that step."
  if (!action && _looksLikeNavigation(message)) {
    await _handleNavigation(message);
    return;
  }

  // NOTE: Manipulation is fully text-driven (see _tryApplyManipulation above).
  // The old Move/Rotate/Scale/Height button palette + part-selection chips were
  // removed — users now type commands like "move 5m north" or "add 2 floors".

  // Optimization — run the REAL backend NSGA-II view-optimizer on the building and
  // SAVED-SHAPES EXPLORER: list every saved version as a selectable chip so the user
  // can preview each in 3D and optimize the one they pick (not just "optimize all").
  if (
    action?.intent === "browse_saved" ||
    /\b(saved (shapes?|options?|versions?)|shape library|explorer of saved|browse saved)\b/i.test(message || "")
  ) {
    const sid = getState().sessionId;
    pushMessage("user", "Show my saved shapes");
    if (!sid) { pushMessage("assistant", "No active session yet."); return; }
    setBusy(true);
    try {
      const r = await api.agent.listDesignOptions(sid);
      const saved = r?.options || [];
      if (!saved.length) {
        pushMessage("assistant", "You have no saved shapes yet. Manipulate a building, then **Save as new shape option** — it'll appear here to preview and optimize.", _manipChips());
        return;
      }
      // One chip per saved version → preview it in 3D, then optimize that one.
      const chips = saved.map((o, i) => ({
        label: `${o.label || o.shape_option_id || `Shape ${i + 1}`}${o.shape_type ? ` · ${o.shape_type}` : ""}`,
        intent: "preview_saved",
        optionId: o.shape_option_id,
      }));
      const lines = saved.map((o, i) =>
        `**${i + 1}.** ${o.shape_option_id}${o.shape_type ? ` · ${o.shape_type}` : ""}${o.created_from_prompt ? ` — _“${o.created_from_prompt}”_` : ""}`
      ).join("\n");
      pushMessage(
        "assistant",
        `🗂️ **Saved shapes** (${saved.length}). Pick one to preview it in 3D, then optimize that exact shape:\n${lines}`,
        chips
      );
    } catch (err) {
      pushMessage("assistant", `⚠️ Couldn't load saved shapes: ${err.message}`);
    } finally {
      setBusy(false);
    }
    return;
  }

  // PREVIEW a chosen saved shape: make it the active building, render it in the 3D
  // viewer, then offer to optimize THIS shape (preserving its manipulated geometry).
  if (action?.intent === "preview_saved" && action?.optionId) {
    const sid = getState().sessionId;
    if (!sid) { pushMessage("assistant", "No active session."); return; }
    const oid = action.optionId;
    pushMessage("user", `Preview saved shape ${oid}`);
    setBusy(true);
    setStatus("Loading saved shape…");
    let selRes = null;
    try {
      selRes = await api.agent.selectDesignOption(sid, oid);
    } catch (err) {
      setBusy(false);
      setStatus("Ready");
      pushMessage("assistant", `⚠️ Couldn't load that saved shape: ${err.message}`);
      return;
    }
    // CRITICAL: point the optimizer at THIS saved shape. The select route makes the
    // saved option the active building with building_id === oid; without updating
    // selectedBuildingId the optimizer keeps targeting the original generated building
    // (stale id) → 404 → "no valid options". Clear any prior optimizationResult so the
    // viewer re-renders the saved shape, not the last run's options.
    setState({
      selectedBuildingId: oid,
      selectedShapeType: selRes?.shape_type || getState().selectedShapeType,
      optimizationResult: null,
      options: [],
    });
    // Tell the user + offer the optimize action IMMEDIATELY — the optimizer only needs
    // the state above, NOT the viewer. The 3D preview is best-effort and must never
    // block the flow (a viewer/import stall was leaving the UI stuck on "Loading…").
    setBusy(false);
    setStatus("Ready");
    pushMessage(
      "assistant",
      `👁️ Loaded **${oid}** (its manipulated geometry — twist / courtyard / added floors are preserved). Optimize this exact shape, or pick another.`,
      [
        { label: "Optimize this shape", intent: "optimize", optimizeScope: "current", primary: true },
        { label: "Back to saved shapes", intent: "browse_saved" },
      ]
    );
    // Best-effort 3D preview — fire-and-forget so a viewer stall can't hang the chat.
    (async () => {
      try {
        const { refreshExplorer, forceViewerRerender } = await import("./agentClient.js");
        await refreshExplorer();
        await forceViewerRerender({ flash: false });
      } catch { /* preview is optional; optimize still works */ }
    })();
    return;
  }

  // show the top-ranked options (NOT an LLM round-trip, NOT random variations).
  // Optimize ALL saved shapes (Fix 5/6): retain each saved geometry, find best
  // placement/rotation/score per shape, show results linked to source option.
  if (action?.intent === "optimize_all_saved") {
    const sid = getState().sessionId;
    pushMessage("user", "Optimize all saved shapes");
    setBusy(true);
    setStatus("Optimizing all saved shapes…");
    try {
      const res = await api.agent.optimizeAllSavedShapes(sid);
      const opts = res?.optimized_options || [];
      if (!opts.length) {
        pushMessage("assistant", "No saved shapes could be optimized — save a manipulated shape first, then try again.");
        return;
      }
      // Feed the optimized results into the options store + comparison.
      setState({ options: opts.map((o) => ({
        option_id: o.optimized_option_id, shape_type: o.shape_type, boundary: o.geometry.boundary,
        footprint: o.geometry.boundary, floors: o.geometry.floors, score: o.scores.total,
        holes: o.geometry.holes || [],
        // Keep the saved shape's manipulated plate stack so the preview renders the real
        // per-floor geometry (twist / added floors), not a flat re-extrusion.
        floor_plates: o.geometry.floor_plates || [],
        rotation_degrees: o.placement.rotation_degrees, source_shape_option_id: o.source_shape_option_id,
        objective_scores: o.scores, validation_report: o.validation_report,
      })), centerView: "compare" });
      const lines = opts.slice(0, 8).map((o, i) =>
        `**${String.fromCharCode(65 + i)}.** ${o.shape_type || "Shape"} (from ${o.source_shape_option_id}) — score ${o.scores.total}, ${o.placement.rotation_degrees}°`
      ).join("\n");
      // Transparency (spec): report which metrics drove the optimization vs which
      // were unavailable — no fabricated scores.
      const used = res.metrics_used || [];
      const unavail = res.metrics_unavailable || [];
      const metricNote = used.length
        ? `\n\n_Optimization used: ${used.join(", ")}.${unavail.length ? ` Unavailable (excluded): ${unavail.join(", ")}.` : ""}_`
        : "";
      pushMessage("assistant", `Optimized **${opts.length} saved shape${opts.length > 1 ? "s" : ""}** (geometry retained, best placement found):\n${lines}${metricNote}`,
        [{ label: "Compare options", message: "compare", intent: "compare" }]);
    } catch (err) {
      pushMessage("assistant", `⚠️ Optimization of saved shapes failed: ${err.message}`);
    } finally {
      setBusy(false);
      setStatus("Ready");
    }
    return;
  }

  // Feature 6 — EVALUATE DESIGN (analysis-only): score the current building across
  // all objectives WITHOUT moving/rotating/scaling. Shows metrics + overall score.
  if (action?.intent === "evaluate" || /^\s*(evaluate( design| the design)?|analy[sz]e( design| performance)?)\s*$/i.test(message || "")) {
    const sid = getState().sessionId;
    if (!sid || !(getState().buildings || []).length) {
      pushMessage("assistant", "Generate or select a shape first, then I can evaluate its performance.");
      return;
    }
    pushMessage("user", "Evaluate design");
    setBusy(true);
    setStatus("Evaluating design…");
    try {
      const res = await api.agent.evaluateDesign(sid);
      const s = res.scores || {};
      recordDecision("evaluation", "evaluate_design", { result: `Overall ${s.overall_score}`, data: s });
      // Transparency: tell the user which context data fed the evaluation.
      const ca = res.context_availability || {};
      const ctxNote = (ca.unavailable && ca.unavailable.length)
        ? `\n\n_Used: ${(ca.used || []).join(", ") || "geometry only"}. Unavailable (defaults used): ${ca.unavailable.join(", ")}._`
        : "";
      pushMessage(
        "assistant",
        `📊 **Design evaluation** (geometry unchanged):\n` +
          `• Solar ${s.solar} · View ${s.view} · Noise ${s.noise} · Wind ${s.wind}\n` +
          `• Access ${s.road_access} · Open Space ${s.open_space} · Density ${s.density}${s.far != null ? ` · FAR ${s.far}` : ""}\n` +
          `• **Overall Score: ${s.overall_score}**${ctxNote}\n\nReady to optimize, or keep editing?`,
        [
          { label: "Optimize", message: "optimize", intent: "optimize" },
          { label: "AI Feedback", message: "Give architectural feedback", intent: "feedback" },
        ]
      );
    } catch (err) {
      pushMessage("assistant", `⚠️ Evaluation failed: ${err.message}`);
    } finally {
      setBusy(false);
      setStatus("Ready");
    }
    return;
  }

  if ((action?.intent === "optimize" || /^optimize/i.test(message || "")) && !action?.optimizeScope) {
    // If the user has TICKED saved shapes (in the gallery / Saved-Shapes folder), the
    // intent is clear: optimize THOSE directly — no scope question. The selection IS
    // the answer. Run it immediately and jump to the comparison.
    const ticked = getState().savedSelection || [];
    if (ticked.length) {
      pushMessage("user", `Optimize ${ticked.length} selected shape${ticked.length > 1 ? "s" : ""}`);
      pushMessage("assistant", `⚙ Optimizing **${ticked.length} selected shape${ticked.length > 1 ? "s" : ""}** — finding the best placements (up to 2 distinct ones each)…`);
      try {
        const { optimizeSavedSelection } = await import("./panels/explorer.js");
        await optimizeSavedSelection([...ticked]);
        // Report what actually landed in the store so a silent empty result is visible
        // (instead of "Done" with an empty Optimization folder). Counts come from the
        // store the explorer + comparison read from.
        const _nVar = (getState().savedOptimized || []).length;
        const _nCmp = (getState().comparisonOptions || []).length;
        if (_nVar > 0) {
          pushMessage("assistant",
            `Done — **${_nVar} optimized variant${_nVar > 1 ? "s" : ""}** ${_nVar > 1 ? "are" : "is"} in the Optimization Explorer (the best distinct placement${_nVar > 1 ? "s" : ""} per shape — a tight site may yield just one) and ready to compare with their originals.`,
            [{ label: "Compare", message: "compare", intent: "compare" }]);
        } else {
          pushMessage("assistant",
            `⚠️ Optimization ran but no variants came back (cmp=${_nCmp}). Re-tick the saved shapes and try again, or tell me and I'll check the backend.`);
        }
      } catch (e) {
        pushMessage("assistant", `⚠️ Optimization failed: ${e.message}`);
      }
      return;
    }
    // No selection → fall back to asking scope (only when saved shapes exist).
    let savedCount = 0;
    try {
      const sid = getState().sessionId;
      if (sid) { const r = await api.agent.listDesignOptions(sid); savedCount = (r?.options || []).length; }
    } catch { /* optional */ }
    if (savedCount > 0) {
      pushMessage("user", "Optimize");
      pushMessage(
        "assistant",
        `You have **${savedCount} saved shape${savedCount > 1 ? "s" : ""}**, none ticked. Tick the shapes you want in **Saved Shapes**, then Optimize — or choose:`,
        [
          { label: "Optimize Current Shape", intent: "optimize", optimizeScope: "current", primary: true },
          { label: "Optimize All Saved Shapes", intent: "optimize_all_saved" },
        ]
      );
      return;
    }
  }

  if (action?.intent === "optimize" || /^optimize/i.test(message || "")) {
    const { canEnter, enterStage } = await import("./core/workflow.js");
    if (!canEnter(STAGES.OPTIMIZE)) {
      pushMessage("user", "Optimize the building placement");
      pushMessage(
        "assistant",
        getState().selectedShapeType
          ? "Generate a building first — describe what you'd like me to create."
          : "Let's pick a shape first. Tell me what you'd like to build and select one from the Shape Library — then I'll optimize it."
      );
      return;
    }
    pushMessage("user", "Optimize the building placement");
    enterStage(STAGES.OPTIMIZE, { announce: true }); // lands on the 3D viewer preview
    setBusy(true);
    setStatus("Optimizing…");
    try {
      const { optimizeBuilding } = await import("./agentClient.js");
      recordDecision("optimization", "optimization_run", { input: "multi-objective optimizer", result: "Pareto optimization started" });
      const res = await optimizeBuilding(action?.optimizeShape ? { optimize_shape: true } : {});
      if (res && (res.options || []).length) {
        const top = res.options[0];
        recordDecision("optimization", "options_generated", {
          result: `${res.options.length} ranked options generated`,
          data: {
            count: res.options.length,
            options: res.options.map((o) => ({ option_id: o.option_id, rank: o.rank, score: o.score })),
          },
        });
        // Show the PREVIEW first: all optimized options placed on the site, each with
        // a floating score card, so the user can see every optimized shape in context
        // before opening the comparison table. Force a FRESH render of the options —
        // activate() alone skips re-rendering when meshes already exist (the placed
        // building was drawn when the OPTIMIZE stage first opened), which left the
        // optimized options + score cards undrawn.
        setState({ centerView: "viewer" });
        try {
          const viewer = await import("./views/viewerView.js");
          viewer.renderScene(getState().site, getState().options || []);
        } catch { /* viewer mounts later */ }
        const strat = top.strategy_name ? `${top.strategy_name} — ` : "";
        pushMessage(
          "assistant",
          `Ran multi-objective optimization (Solar · View · Noise · Open Space · Density · Wind) — **${res.options.length} distinct options** are now previewed on the site, each with its score card.\n` +
            `Best: ${strat}score ${Number(top.score).toFixed(0)}${Number.isFinite(Number(top.view_score)) ? `, view ${Number(top.view_score).toFixed(0)}` : ""}${top.far != null ? `, FAR ${top.far}` : ""}. ` +
            "Click a shape on the site to select it, or open the full comparison table:",
          [
            { label: "Compare details", message: "compare", intent: "compare" },
            { label: "Re-optimize (shape morph)", message: "optimize shape", intent: "optimize", optimizeShape: true },
          ]
        );
      } else {
        pushMessage("assistant", "Optimization returned no valid options for this building/site. Try a smaller building or a larger site.");
      }
    } finally {
      setBusy(false);
      setStatus("Ready");
    }
    return;
  }

  // Compare / Export are view/download actions over the REAL backend data we
  // already hold — no agent round-trip needed.
  if (action?.intent === "compare") {
    pushMessage("user", "Compare the current options");
    const { canEnter, enterStage } = await import("./core/workflow.js");
    if (!canEnter(STAGES.COMPARE)) {
      pushMessage("assistant", "Run optimization first so there are ranked options to compare.");
      return;
    }
    // Build the comparison set ROBUSTLY.
    // 1) PREFER comparisonOptions when it already holds a real comparison set WITH scores —
    //    optimizeSavedSelection() builds these correctly (baselines + S01A/S01B variants,
    //    each carrying objective_scores + score). Rebuilding from savedOptimized here was
    //    DROPPING those scores (baselines got objective_scores:{}, score:null) and could
    //    show only 1 option — that's the "0.0 / N/A / 1 option" bug in the screenshot.
    // 2) Only fall back to the persisted savedOptimized rebuild when comparisonOptions is
    //    empty or scoreless (e.g. a main-optimize run clobbered it with a single option).
    const _cmp = getState().comparisonOptions || [];
    const _cmpHasScores = _cmp.length >= 2 && _cmp.some(
      (o) => o && (o.objective_scores && Object.keys(o.objective_scores).length) || Number.isFinite(Number(o?.score)));
    const _sv = getState().savedShapes || [];
    const _opt = getState().savedOptimized || [];
    let opts;
    if (_cmpHasScores) {
      opts = _cmp;
    } else if (_opt.length) {
      // Persisted fallback: carry each saved baseline's REAL scores (not empty objects) so
      // the table still shows numbers, plus the optimized variants.
      const baselines = _sv.map((b) => ({
        option_id: b.shape_option_id, label: b.shape_option_id + " (original)",
        shape_type: b.shape_type, is_baseline: true,
        objective_scores: b.objective_scores || b.scores || {},
        score: (b.scores || b.objective_scores || {}).total ?? b.score ?? null,
        boundary: b.boundary, footprint: b.boundary, holes: b.holes || [],
        floors: b.floors,
      }));
      opts = [...baselines, ..._opt];
    } else {
      opts = _cmp.length ? _cmp : getState().options;
    }
    // DEDUPE by option_id — the same shape could appear twice (a freshly-scored copy AND
    // a persisted scoreless copy), which showed duplicate columns where one was 0.0/N/A.
    // Keep the version that HAS scores so each option appears once, fully populated.
    const _scored = (o) => Number.isFinite(Number(o?.score))
      || (o?.objective_scores && Object.keys(o.objective_scores).length > 0);
    const _byId = new Map();
    for (const o of (opts || [])) {
      const id = o.option_id;
      const prev = _byId.get(id);
      if (!prev || (_scored(o) && !_scored(prev))) _byId.set(id, o);
    }
    opts = [..._byId.values()];
    enterStage(STAGES.COMPARE, { announce: false, extraState: { comparisonOptions: opts } });
    recordDecision("comparison", "comparison_opened", {
      result: `Comparing ${opts?.length || 0} options`,
      data: { option_ids: (opts || []).map((o) => o.option_id) },
    });
    const { dispatchView: dv } = await import("./panels/center.js");
    await dv({ type: "compare", payload: { action: "compare" } });
    // Offer to pick the final option (for export) — one chip per option.
    const finalChips = (opts || []).slice(0, 4).map((o, i) => ({
      label: `Select Option ${i + 1} as final`,
      message: `select option ${i + 1} as final`,
      intent: "select_final",
      optionId: o.option_id,
    }));
    pushMessage(
      "assistant",
      `Comparing ${opts?.length || 0} option(s) on score, view, FAR, coverage, setback and ` +
        "constraints. **Pick the final option** to carry to export:",
      finalChips
    );
    return;
  }

  // Final option selection — marks the chosen option for export + decision graph.
  if (action?.intent === "select_final") {
    const opts = getState().options || [];
    const opt = opts.find((o) => o.option_id === action.optionId) || opts[0];
    if (!opt) {
      pushMessage("assistant", "No option to select — run optimization first.");
      return;
    }
    pushMessage("user", `Select ${opt.option_id} as final`);
    // Build the final-option payload the export route expects (metric building).
    const m = opt.constraint_report?.metrics || {};
    const finalPayload = {
      option_id: opt.option_id, boundary: opt.footprint, score: opt.score,
      height_m: opt.height, floors: opt.floors, footprint_area: m.footprint_area,
      far: m.far, building_use: m.building_use,
    };
    setState({ selectedFinalOption: finalPayload, selectedOptionId: opt.option_id });
    try {
      if (getState().sessionId) await api.agent.selectFinalOption(getState().sessionId, opt.option_id, finalPayload);
    } catch (e) { /* sync best-effort */ }
    recordDecision("comparison", "final_option_selected", {
      input: opt.option_id, result: "Final option chosen", data: { score: opt.score },
    });
    const { enterStage } = await import("./core/workflow.js");
    enterStage(STAGES.EXPORT, { announce: false });
    pushMessage(
      "assistant",
      `✅ **${opt.option_id}** selected as the final design (score ${Number(opt.score).toFixed(2)}, ` +
        `${opt.floors || "?"} floors). Export it:`,
      [
        { label: "Export Rhino (.3dm)", message: "export rhino", intent: "export_rhino" },
        { label: "Export Revit-compatible IFC (.ifc)", message: "export ifc", intent: "export_ifc" },
        { label: "Decision tree", message: "decision tree", intent: "decision" },
      ]
    );
    return;
  }
  // Decision tree — design-evolution graph. Gated so it can't open before there
  // is any design history.
  if (action?.intent === "decision") {
    pushMessage("user", "Show the decision tree");
    const { canEnter, enterStage } = await import("./core/workflow.js");
    if (!canEnter(STAGES.DECISION)) {
      pushMessage("assistant", "There's no design history yet — generate a building first.");
      return;
    }
    enterStage(STAGES.DECISION, { announce: false });
    const { dispatchView: dv } = await import("./panels/center.js");
    await dv({ type: "decision", payload: { action: "decision" } });
    pushMessage("assistant", "Here's the decision graph of how the design evolved. Ready to export when you are.", [
      { label: "Export", message: "export", intent: "export" },
    ]);
    return;
  }
  // Real exports of the FINAL selected option (or first building as fallback).
  if (action?.intent === "export_rhino" || action?.intent === "export_ifc") {
    const sid = getState().sessionId;
    if (!sid) { pushMessage("assistant", "Generate and select a building first."); return; }
    const isRhino = action.intent === "export_rhino";
    const fmt = isRhino ? "Rhino (.3dm)" : "Revit-compatible IFC (.ifc)";
    pushMessage("user", `Export ${fmt}`);
    const url = isRhino ? api.agent.exportSelectedRhinoUrl(sid) : api.agent.exportSelectedIfcUrl(sid);
    window.open(url, "_blank");
    recordDecision("export", isRhino ? "export_rhino" : "export_ifc", {
      result: `Exported final option as ${fmt}`,
      data: { option_id: getState().selectedFinalOption?.option_id },
    });
    pushMessage(
      "assistant",
      `📦 Exported the final selected option as **${fmt}** — includes the confirmed site boundary, ` +
        "the selected building (extruded to its height with per-floor storeys), and metadata " +
        "(option id, score, floors, FAR). " +
        (isRhino ? "Open it in Rhino." : "Import it into Revit (File → Import → IFC).") +
        " Want to review the decision tree?",
      [{ label: "Decision tree", message: "decision tree", intent: "decision" }]
    );
    return;
  }
  // Legacy generic export (GeoJSON) — kept as a fallback.
  if (action?.intent === "export") {
    pushMessage("user", "Export the design");
    pushMessage("assistant", "Pick an export format for the final design:", [
      { label: "Rhino (.3dm)", message: "export rhino", intent: "export_rhino" },
      { label: "Revit-compatible IFC (.ifc)", message: "export ifc", intent: "export_ifc" },
    ]);
    return;
  }

  // Free-text manipulation command (no armed tool, no chip): "move building 5m
  // north", "rotate right wing 10 degrees", "scale 1.2". Detect intent + target
  // part from the text and apply directly via the backend.
  if (!action && (getState().buildings || []).length) {
    const cmd = _parseFreeManip(message);
    if (cmd) {
      await _applyFreeManip(message, cmd);
      return;
    }
    // Once a shape is selected and we're EDITING it, route ALL remaining free text to
    // the manipulation backend — its 3-layer understanding (direct command → semantic
    // intent → reason node) handles "move away from noise", "move to the centre",
    // "increase footprint", "open it toward the park", etc. that no narrow frontend
    // keyword list would catch. The backend decides what to do AND, when it genuinely
    // can't map the prompt, returns an honest "Action failed: ... Try ..." — so design
    // text NEVER silently falls through to the agent SSE's generic "Done." We skip only
    // shape-GENERATION prompts (handled earlier, before a shape is selected).
    const editing = getState().selectedShapeType || getState().stage !== STAGES.SHAPES;
    if (editing) {
      await _applyArchitecturalFeedback(message);
      return;
    }
  }

  pushMessage("user", message);
  setBusy(true);
  setStatus("Working…");
  try {
    const stage = getState().stage;
    if (stage === STAGES.SITE) {
      await handleSite(message);
    } else if (stage === STAGES.BOUNDARY) {
      await handleBoundary(message, action);
    } else {
      await handleAgent(message);
    }
  } catch (err) {
    console.error("[copilot] send failed", err);
    pushMessage("assistant", `⚠️ ${err.message || "Something went wrong."}`);
    setStatus("Error");
  } finally {
    setBusy(false);
  }
}

// First-load greeting. A fresh page begins a new project at the SITE stage.
export async function greet() {
  setState({ stage: STAGES.SITE, centerView: "map" });
  pushMessage(
    "assistant",
    "Welcome to **TerraPilot**. Enter a site location to begin — a place name " +
      "(e.g. *Bangalore*), an address, or coordinates like *12.9716, 77.5946*."
  );
  setStatus("Ready · Site");
  // Probe the agent backend in the background so later stages know availability.
  try {
    const { ensureAgentAvailable } = await import("./agentClient.js");
    ensureAgentAvailable();
  } catch {
    /* non-fatal */
  }
}
