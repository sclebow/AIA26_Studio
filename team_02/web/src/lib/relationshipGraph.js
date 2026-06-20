// Pure builder for the Relationship Galaxy: turn + persona + the static model →
// { nodes, links } for 3d-force-graph. One multi-partite graph carrying ALL the
// data (see docs/adr-relationship-galaxy.md).
//
// COMPLEXITY is now expressed as MEANING LENSES, not arbitrary L1/L2/L3 tiers:
//   base     — senses + rooms (always shown; never empty)
//   problems — rooms driving sense issues (exhibits) + room→room bleed (transmission)
//   levers   — design levers + lever→sense fixes
//   healthy  — conflict-free structural adjacency
//   ripple   — sense↔sense couplings (also arms the ripple simulation)
// Lenses compose (multi-toggle). Each node carries `group` (its community anchor)
// and each link carries `curvature`/`curveRot` for the bundled-fiber look.
import { SENSES, SC, SI } from "./constants.js";
import { SENSE_SENSE, LEVER_SENSE, thresholdFromWeight } from "./senseModel.js";

const FG = "rgba(240,237,232,";                 // foreground, append "<alpha>)"
const PROV = { verified: { basis: "research" }, inferred: { basis: "physics" } };
const parse = (s) => { try { return s ? JSON.parse(s) : null; } catch { return null; } };

// deterministic 0..2π rotation from a key, so parallel arcs fan into a ribbon
function rot(str) {
  let h = 0; for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
  return (h % 628) / 100;
}
// the sense a room scores worst on — its community anchor
function worstSense(r) {
  let best = SENSES[0], bv = r.comfortScores?.[SENSES[0]] ?? 1;
  for (const s of SENSES) { const v = r.comfortScores?.[s] ?? 1; if (v < bv) { bv = v; best = s; } }
  return best;
}

// ── Shared join context (reused by the builder AND lib/galaxyChildren.js) ──
export function buildContext(turn, persona) {
  const rooms = parse(turn?.scores_json)?.rooms || [];
  const gd = turn?.graph_data || {};
  const weights = persona?.comfort_weights || {};
  const thr = (s) => thresholdFromWeight(weights[s] ?? 0.5);
  const byName = {}; rooms.forEach((r) => { byName[r.roomName] = r; });
  const idToName = {}; (gd.nodes || []).forEach((n) => { idToName[n.id] = n.name; });
  const meta = {}; (gd.nodes || []).forEach((n) => { meta[n.name] = n; });
  const maxDeg = Math.max(1, ...(gd.nodes || []).map((n) => n.degree || 0));
  const fail = {}; SENSES.forEach((s) => { fail[s] = 0; });
  rooms.forEach((r) => SENSES.forEach((s) => { if ((r.comfortScores?.[s] ?? 1) < thr(s)) fail[s]++; }));
  return { rooms, gd, weights, thr, byName, idToName, meta, maxDeg, fail };
}

// ── Base node emitters (always present) ──
function emitSenses(ctx, nodes) {
  SENSES.forEach((s) => nodes.push({
    id: `sense:${s}`, kind: "sense", sense: s, group: s, isCentroidLabel: true,
    label: `${SI[s]} ${s}`, color: SC[s], val: 16 + Math.min(ctx.fail[s], 6) * 2.5, fail: ctx.fail[s],
  }));
}
function emitRooms(ctx, nodes) {
  ctx.rooms.forEach((r) => {
    const m = ctx.meta[r.roomName] || {};
    nodes.push({
      id: `room:${r.roomName}`, kind: "room", label: r.roomName, group: worstSense(r),
      color: "rgba(228,230,236,0.92)", val: 5 + ((m.degree || 0) / ctx.maxDeg) * 4,
      overall: r.overallScore, roomId: r.roomId,
      degree: m.degree ?? 0, betweenness: m.betweenness ?? 0, bridge: !!m.is_bridge,
      isolated: !!m.isolated, rtype: m.room_type,
    });
  });
}

// ── Lens emitters ──
function emitLeverNodes(ctx, nodes) {
  [...new Set(LEVER_SENSE.map((l) => l[0]))].forEach((lv) => {
    const tgt = (LEVER_SENSE.find((l) => l[0] === lv) || [])[1];
    nodes.push({ id: `lever:${lv}`, kind: "lever", label: lv, group: tgt, color: "rgba(26,26,30,0.92)", val: 1.5 });
  });
}
function emitCoupling(ctx, links) {
  SENSE_SENSE.forEach(([a, b, dir, sign, tier, mech], i) => {
    const p = PROV[tier] || PROV.inferred;
    links.push({
      source: `sense:${a}`, target: `sense:${b}`, kind: "coupling", sign, mech, basis: p.basis,
      color: SC[a], width: 1.4, opacity: tier === "verified" ? 0.65 : 0.34,
      arrow: dir !== "both", curvature: 0.3, curveRot: rot(`c${i}`),
    });
  });
}
function emitTransmission(ctx, links) {
  (ctx.gd.edges || []).forEach((e) => {
    const an = ctx.idToName[e.source], bn = ctx.idToName[e.target];
    const a = ctx.byName[an], b = ctx.byName[bn];
    if (!a || !b) return;
    const conflicts = e.transmissive_conflicts || [];
    if (!conflicts.length) return;
    const sev = conflicts.map((s) => ({ s, worse: Math.min(a.comfortScores?.[s] ?? 1, b.comfortScores?.[s] ?? 1),
      sa: a.comfortScores?.[s] ?? 1, sb: b.comfortScores?.[s] ?? 1 })).sort((x, y) => x.worse - y.worse);
    const w = sev[0];
    const src = w.sa <= w.sb ? an : bn, tgt = w.sa <= w.sb ? bn : an;
    links.push({ source: `room:${src}`, target: `room:${tgt}`, kind: "transmission", sense: w.s, sign: "-",
      mech: `${w.s} bleeds across the door`, door: e.door_name, color: SC[w.s],
      width: 1.5 + (1 - w.worse) * 3, opacity: 0.42 + (1 - w.worse) * 0.45, arrow: true, curvature: 0.2, curveRot: rot(src + tgt) });
  });
}
function emitStructure(ctx, links) {
  (ctx.gd.edges || []).forEach((e) => {
    const an = ctx.idToName[e.source], bn = ctx.idToName[e.target];
    if (!ctx.byName[an] || !ctx.byName[bn]) return;
    if ((e.transmissive_conflicts || []).length) return;
    links.push({ source: `room:${an}`, target: `room:${bn}`, kind: "structure",
      color: `${FG}0.22)`, width: 0.5, opacity: 0.3, curvature: 0.12, curveRot: rot("s" + an + bn) });
  });
}
function emitExhibits(ctx, links) {
  ctx.rooms.forEach((r) => SENSES.forEach((s) => {
    const v = r.comfortScores?.[s] ?? 1;
    if (v < ctx.thr(s)) links.push({ source: `room:${r.roomName}`, target: `sense:${s}`, kind: "exhibits",
      sense: s, sign: "-", mech: `${s} below threshold here (${v.toFixed(2)})`, color: SC[s],
      width: 1 + (ctx.thr(s) - v) * 4, opacity: 0.3 + (ctx.thr(s) - v) * 0.6, arrow: true, curvature: 0.35, curveRot: rot("e" + r.roomName + s) });
  }));
}
function emitLeverLinks(ctx, links) {
  LEVER_SENSE.forEach(([lv, s, sign, tier, mech], i) => {
    const p = PROV[tier] || PROV.inferred;
    links.push({ source: `lever:${lv}`, target: `sense:${s}`, kind: "lever", sign, mech, basis: p.basis,
      color: `${FG}0.35)`, width: 0.8, opacity: 0.22, arrow: true, curvature: 0.15, curveRot: rot("l" + i) });
  });
}

// ── The lenses (multi-toggle; compose over the always-on base) ──
export const LENSES = [
  { key: "problems", label: "problems", desc: "where comfort fails — rooms driving sense issues + bleed between rooms", emitLinks: [emitExhibits, emitTransmission] },
  { key: "levers",   label: "levers",   desc: "design moves you can pull — what each lever improves", emitNodes: [emitLeverNodes], emitLinks: [emitLeverLinks] },
  { key: "healthy",  label: "healthy",  desc: "the calm structure — conflict-free room adjacencies", emitLinks: [emitStructure] },
  { key: "ripple",   label: "ripple",   desc: "how the senses talk — the couplings (click a sense / ▶ to animate)", emitLinks: [emitCoupling] },
];

export const DEFAULT_LENSES = ["problems"];
const LEVEL_TO_LENSES = {                         // shim for any legacy numeric caller
  1: ["problems", "ripple"], 2: ["problems", "levers", "ripple"],
  3: ["problems", "levers", "healthy", "ripple"],
};

function normalizeLenses(lenses) {
  if (lenses instanceof Set) return lenses;
  if (Array.isArray(lenses)) return new Set(lenses);
  if (typeof lenses === "number") return new Set(LEVEL_TO_LENSES[lenses] || DEFAULT_LENSES);
  return new Set(DEFAULT_LENSES);
}

export function buildRelationshipGraph(turn, persona, lenses = DEFAULT_LENSES) {
  const keys = normalizeLenses(lenses);
  const ctx = buildContext(turn, persona);
  const nodes = [], links = [];
  if (!ctx.rooms.length) return { nodes, links };
  emitSenses(ctx, nodes);
  emitRooms(ctx, nodes);
  LENSES.forEach((L) => {
    if (!keys.has(L.key)) return;
    (L.emitNodes || []).forEach((fn) => fn(ctx, nodes));
    (L.emitLinks || []).forEach((fn) => fn(ctx, links));
  });
  return { nodes, links };
}

// Legend rows describing the galaxy's encodings (used by the overlay).
export const GALAXY_LEGEND = [
  ["sense", "the 6 senses — hue = identity, size = rooms failing it"],
  ["room", "a room — size = how connected (doors), grouped near its weakest sense"],
  ["lever", "a design lever — what an edit moves"],
  ["coupling", "sense ↔ sense (research bright · physics faint) — the ripple"],
  ["transmission", "a sense bleeding room → room"],
  ["exhibits", "a room driving a sense problem"],
  ["fix", "a lever that improves a sense"],
];

// ── Educational layer ("The Narrator") ──────────────────────────────────────
// Plain-language copy that translates the galaxy's encoding for a cold viewer.
// Pure strings + read helpers; NO change to the graph model. Consumed by
// galaxy/RelationshipGalaxy.jsx + galaxy/GalaxyNarrator.jsx.
const SENSE_WORD = { thermal: "warmth", visual: "light", acoustic: "sound", spatial: "space", olfactory: "smell", tactile: "touch" };
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const senseWord = (s) => SENSE_WORD[s] || s;
const senseFull = (s) => `${senseWord(s)} (${s})`;
const nameOf = (x) => { const id = x && typeof x === "object" ? x.id : x; const str = String(id || ""); const i = str.indexOf(":"); return i >= 0 ? str.slice(i + 1) : str; };
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

// what each control teaches (lens pills + fiber / ▶ buttons)
const CONTROL_COPY = {
  problems: { tag: "lens · problems", title: "Problems lens", body: "Where comfort fails — the rooms driving sense issues, and where a sense leaks from one room into the next." },
  levers:   { tag: "lens · levers",   title: "Levers lens",   body: "Design moves you can pull, and which sense each one improves." },
  healthy:  { tag: "lens · healthy",  title: "Healthy lens",  body: "The calm structure — rooms that sit comfortably together, with no sense conflict between them." },
  ripple:   { tag: "lens · ripple",   title: "Ripple lens",   body: "How the senses talk to each other. Turn it on, then click a sense (or press ▶) to watch the effect travel." },
  fiber:    { tag: "view · fiber",    title: "Fiber view",    body: "Dissolves the spheres and leaves only the threads — the bare shape of how everything connects." },
  play:     { tag: "ripple",          title: "Play the ripple", body: "Sends a ripple through the senses, worst-scoring first. Needs the ripple lens turned on." },
};

export const GALAXY_GUIDE = {
  // first-look orientation — each beat names one part of the picture in plain words.
  // `focus` drives the reused spotlight (fade everything but this element type).
  tour: [
    { focus: "all",   title: "Your home, read as comfort", body: "Six senses, your rooms, and the threads of how they pull on each other — the whole picture in one view." },
    { focus: "sense", title: "The six senses",  body: "These glowing labels are what Sensi scores: warmth, light, sound, space, smell and touch. The colour names the sense; a bigger label means more rooms struggle with it." },
    { focus: "room",  title: "Your rooms",      body: "Each grey sphere is a room. It drifts toward the sense it struggles with most — so where it floats is already a clue." },
    { focus: "fiber", title: "The threads between them", body: "Threads are how comfort travels — one sense tugging another, or a problem leaking between rooms. Brighter threads are research-backed; faint, dashed ones are physics-based." },
    { focus: "all",   title: "Now it's yours",  body: "Hover anything to read it in plain words. Toggle a lens up top to change what the threads show. You can dismiss this guide whenever you like." },
  ],
  idle: "Hover any sphere or thread to read it in plain words · toggle a lens to change what's shown",

  // hover/select readouts — translate a node or a fiber into one warm sentence.
  readNode(n) {
    if (!n) return null;
    if (n.kind === "sense") {
      const w = senseWord(n.sense);
      const body = n.fail > 0
        ? `Struggling in ${plural(n.fail, "room")} right now. Click to ripple how ${w} pulls on the other senses.`
        : `No rooms are struggling with ${w} right now. Click to ripple how ${w} touches the other senses.`;
      return { tag: `sense · ${n.sense}`, title: `${SI[n.sense] || ""} ${cap(w)}`.trim(), body };
    }
    if (n.kind === "room") {
      const bits = [`Its weakest sense is ${senseFull(n.group)}.`];
      if (n.degree > 0) bits.push(`Connected by ${plural(n.degree, "door")}.`);
      if (n.bridge) bits.push("A structural link between areas.");
      else if (n.isolated) bits.push("A little cut off from the rest.");
      bits.push("Click to open its senses and neighbours.");
      return { tag: "room", title: n.label, body: bits.join(" ") };
    }
    if (n.kind === "lever") return { tag: "lever", title: n.label, body: "A design move you can pull — click to see which sense it improves." };
    if (n.kind === "score") return { tag: "score", title: n.label, body: "One room's score for a single sense." };
    return null;
  },
  readLink(l) {
    if (!l) return null;
    const a = nameOf(l.source), b = nameOf(l.target);
    if (l.kind === "coupling") {
      const verb = l.sign === "+" ? "lift each other" : l.sign === "-" ? "pull against each other" : "shape each other";
      return { tag: "coupling", title: `${cap(senseWord(a))} ↔ ${cap(senseWord(b))}`,
        body: `${cap(senseWord(a))} and ${senseWord(b)} ${verb} — ${l.mech}. ${l.basis === "research" ? "Research-backed." : "Physics-inferred."}` };
    }
    if (l.kind === "transmission") return { tag: "transmission", title: "Leaking room to room",
      body: `${a}'s ${senseWord(l.sense)} drifts into ${b}${l.door ? " — they share a door" : ""}.` };
    if (l.kind === "exhibits") return { tag: "exhibits", title: "A room driving a problem",
      body: `${a}'s ${senseWord(l.sense)} falls below comfort.` };
    if (l.kind === "structure") return { tag: "structure", title: "A calm connection",
      body: `${a} and ${b} share a door with no sense conflict.` };
    if (l.kind === "lever") return { tag: "fix", title: "A design fix", body: `${a} improves ${senseWord(b)}.` };
    return null;
  },
  control: (k) => CONTROL_COPY[k] || null,
};
