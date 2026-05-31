// Pure builder for the Relationship Galaxy: turn + persona + the static model →
// { nodes, links } for 3d-force-graph. One multi-partite graph carrying ALL the
// data (see docs/adr-relationship-galaxy.md). `level` is the complexity tier:
//   L1 essentials  — verified sense couplings + room→room transmission
//   L2 full        — + inferred couplings + lever→sense fixes + room→sense problems
//   L3 everything  — + healthy structural edges + personality (when present)
import { SENSES, SC, SI } from "./constants.js";
import { SENSE_SENSE, LEVER_SENSE, thresholdFromWeight } from "./senseModel.js";

const FG = "rgba(240,237,232,";                 // foreground, append "<alpha>)"
const PROV = { verified: { basis: "research", op: 1.0 }, inferred: { basis: "physics", op: 0.5 } };
const parse = (s) => { try { return s ? JSON.parse(s) : null; } catch { return null; } };

export function buildRelationshipGraph(turn, persona, level = 3) {
  const rooms = parse(turn?.scores_json)?.rooms || [];
  const gd = turn?.graph_data || {};
  const weights = persona?.comfort_weights || {};
  const nodes = [];
  const links = [];
  if (!rooms.length) return { nodes, links };

  const thr = (s) => thresholdFromWeight(weights[s] ?? 0.5);
  const byName = {}; rooms.forEach((r) => { byName[r.roomName] = r; });
  const idToName = {}; (gd.nodes || []).forEach((n) => { idToName[n.id] = n.name; });
  const meta = {}; (gd.nodes || []).forEach((n) => { meta[n.name] = n; });
  const maxDeg = Math.max(1, ...(gd.nodes || []).map((n) => n.degree || 0));

  // ── sense nodes (hue + glyph; size = how many rooms fail that sense) ──
  const fail = {}; SENSES.forEach((s) => { fail[s] = 0; });
  rooms.forEach((r) => SENSES.forEach((s) => { if ((r.comfortScores?.[s] ?? 1) < thr(s)) fail[s]++; }));
  SENSES.forEach((s) => nodes.push({
    id: `sense:${s}`, kind: "sense", sense: s, label: `${SI[s]} ${s}`, color: SC[s],
    val: 6 + fail[s] * 3, fail: fail[s],
  }));

  // ── room nodes (size = degree; carries topology metrics) ──
  rooms.forEach((r) => {
    const m = meta[r.roomName] || {};
    nodes.push({
      id: `room:${r.roomName}`, kind: "room", label: r.roomName, color: "rgba(146,144,138,0.9)",
      val: 5 + ((m.degree || 0) / maxDeg) * 12, overall: r.overallScore,
      degree: m.degree ?? 0, betweenness: m.betweenness ?? 0, bridge: !!m.is_bridge,
      isolated: !!m.isolated, rtype: m.room_type,
    });
  });

  // ── lever nodes (the actionable "how to fix" layer) — L2+ ──
  if (level >= 2) {
    [...new Set(LEVER_SENSE.map((l) => l[0]))].forEach((lv) =>
      nodes.push({ id: `lever:${lv}`, kind: "lever", label: lv, color: `${FG}0.45)`, val: 3 }));
  }

  // ── coupling links: sense ↔ sense ──
  SENSE_SENSE.forEach(([a, b, dir, sign, tier, mech]) => {
    if (level < 2 && tier !== "verified") return;
    const p = PROV[tier] || PROV.inferred;
    links.push({
      source: `sense:${a}`, target: `sense:${b}`, kind: "coupling", sign, mech, basis: p.basis,
      color: SC[a], width: 1.4, opacity: p.op, arrow: dir !== "both", particles: dir !== "both" ? 2 : 0,
    });
  });

  // ── transmission links: room → room (worst bleeding sense, worse→better) ──
  (gd.edges || []).forEach((e) => {
    const an = idToName[e.source], bn = idToName[e.target];
    const a = byName[an], b = byName[bn];
    if (!a || !b) return;
    const conflicts = e.transmissive_conflicts || [];
    if (!conflicts.length) {
      if (level >= 3) links.push({ source: `room:${an}`, target: `room:${bn}`, kind: "structure", color: `${FG}0.22)`, width: 0.5, opacity: 0.4 });
      return;
    }
    const sev = conflicts.map((s) => ({ s, worse: Math.min(a.comfortScores?.[s] ?? 1, b.comfortScores?.[s] ?? 1),
      sa: a.comfortScores?.[s] ?? 1, sb: b.comfortScores?.[s] ?? 1 })).sort((x, y) => x.worse - y.worse);
    const w = sev[0];
    const src = w.sa <= w.sb ? an : bn, tgt = w.sa <= w.sb ? bn : an;
    links.push({ source: `room:${src}`, target: `room:${tgt}`, kind: "transmission", sense: w.s, sign: "-",
      mech: `${w.s} bleeds across the door`, color: SC[w.s], width: 1.5 + (1 - w.worse) * 3, opacity: 0.95,
      arrow: true, particles: 3 });
  });

  // ── room → sense problems (which rooms drive which sense issues) — L2+ ──
  if (level >= 2) {
    rooms.forEach((r) => SENSES.forEach((s) => {
      const v = r.comfortScores?.[s] ?? 1;
      if (v < thr(s)) links.push({ source: `room:${r.roomName}`, target: `sense:${s}`, kind: "exhibits",
        sense: s, sign: "-", mech: `${s} below threshold here (${v.toFixed(2)})`, color: SC[s],
        width: 1 + (thr(s) - v) * 4, opacity: 0.7, particles: 1, arrow: true });
    }));
  }

  // ── lever → sense fixes — L2+ ──
  if (level >= 2) {
    LEVER_SENSE.forEach(([lv, s, sign, tier, mech]) => {
      const p = PROV[tier] || PROV.inferred;
      links.push({ source: `lever:${lv}`, target: `sense:${s}`, kind: "lever", sign, mech, basis: p.basis,
        color: `${FG}0.35)`, width: 0.8, opacity: p.op * 0.7, arrow: true, particles: 0 });
    });
  }

  return { nodes, links };
}

// Legend rows describing the galaxy's encodings (used by the overlay).
export const GALAXY_LEGEND = [
  ["sense", "the 6 senses — hue = identity, size = rooms failing it"],
  ["room", "a room — size = how connected (doors)"],
  ["lever", "a design lever — what an edit moves"],
  ["coupling", "sense ↔ sense (research bright · physics faint)"],
  ["transmission", "a sense bleeding room → room (particles flow)"],
  ["exhibits", "a room driving a sense problem"],
  ["fix", "a lever that improves a sense"],
];
