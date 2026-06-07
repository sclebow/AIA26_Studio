// The ripple, simulated across the galaxy: an ordered set of pulse-bursts spreading
// from a source sense along the sense↔sense couplings, hop by hop. Pure — the view
// resolves each step to a live coupling link and emits particles along it.
//   color  = valence (green lift / red drag / amber trade-off)  — relationships.VALENCE
//   count/speed = magnitude (realized per-room delta if a room is given, else canonical)
//   delay  = hop * hopGap (direct partners first, then theirs)  — motion.DUR
import { SENSE_SENSE } from "./senseModel.js";
import { VALENCE } from "./relationships.js";
import { DUR } from "./motion.js";

function adjacency() {
  const adj = {};
  SENSE_SENSE.forEach(([a, b, dir, sign]) => {
    (adj[a] || (adj[a] = [])).push({ to: b, sign });
    if (dir === "both") (adj[b] || (adj[b] = [])).push({ to: a, sign });
  });
  return adj;
}

const BASE_MAG = { "-": 0.06, "±": 0.05, "+": 0.04, "0": 0 };

export function rippleSequence(source, { room, hopGap = DUR.slow * 1000, maxHop = 3 } = {}) {
  const adj = adjacency();
  const seq = [];
  const seen = new Set([source]);
  let frontier = [source];
  for (let hop = 0; hop < maxHop && frontier.length; hop++) {
    const next = [];
    frontier.forEach((from) => {
      (adj[from] || []).forEach(({ to, sign }) => {
        if (seen.has(to)) return;
        let mag = BASE_MAG[sign] ?? 0;
        const a = (room?.adjustments || []).find((x) => x.from === from && x.sense === to);
        if (a) mag = Math.abs(a.delta);
        if (mag <= 0) return;
        const v = VALENCE[sign] || VALENCE["0"];
        seq.push({ from, to, sign, color: v.tint, delay: hop * hopGap,
          count: Math.round(1 + mag * 40), speed: 0.004 + mag * 0.05 });
        next.push(to); seen.add(to);
      });
    });
    frontier = next;
  }
  return seq;
}

// The overall worst sense — most rooms failing it, tie-break lowest mean score.
export function worstSense(rooms, senses, thr) {
  let best = senses[0], bestFail = -1, bestMean = 2;
  senses.forEach((s) => {
    let fail = 0, sum = 0, n = 0;
    rooms.forEach((r) => { const v = r.comfortScores?.[s] ?? 1; n++; sum += v; if (v < thr(s)) fail++; });
    const mean = n ? sum / n : 1;
    if (fail > bestFail || (fail === bestFail && mean < bestMean)) { best = s; bestFail = fail; bestMean = mean; }
  });
  return best;
}
