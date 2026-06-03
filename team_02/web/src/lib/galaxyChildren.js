// Expand-in-place: what a node reveals when you fly into it. Pure
// childrenOf(node, ctx) → { nodes, links } using the same join ctx as the builder
// (see buildContext in relationshipGraph.js). Every child node carries `parent` and
// every child link carries `owner` (= the clicked node id) so collapse is exact.
import { SENSES, SC } from "./constants.js";
import { SENSE_SENSE, LEVER_SENSE } from "./senseModel.js";

const FG = "rgba(240,237,232,";

function worstSense(r) {
  let best = SENSES[0], bv = r.comfortScores?.[SENSES[0]] ?? 1;
  for (const s of SENSES) { const v = r.comfortScores?.[s] ?? 1; if (v < bv) { bv = v; best = s; } }
  return best;
}

export function childrenOf(node, ctx) {
  const nodes = [], links = [];
  const owner = node.id;
  const addNode = (n) => nodes.push({ ...n, parent: owner, expand: true });
  const addLink = (l) => links.push({ ...l, owner, curveRot: 0 });

  if (node.kind === "room") {
    const r = ctx.byName[node.label];
    if (!r) return { nodes, links };
    // the room's own six sense scores — a 3D mini-rose around the room
    SENSES.forEach((s) => {
      const v = r.comfortScores?.[s] ?? 1;
      const id = `score:${node.label}:${s}`;
      addNode({ id, kind: "score", sense: s, group: node.group, label: `${s} ${v.toFixed(2)}`,
        color: SC[s], val: 3 + (1 - v) * 5 });
      addLink({ source: node.id, target: id, kind: "has-score", sense: s,
        color: SC[s], width: 1 + (1 - v) * 3, opacity: 0.5, curvature: 0.08 });
    });
    // the room's own senses talk to each other — its internal sense network (a 3D SenseHub)
    SENSE_SENSE.forEach(([a, b, dir, sign]) => {
      addLink({ source: `score:${node.label}:${a}`, target: `score:${node.label}:${b}`, kind: "coupling", sign,
        color: SC[a], width: 1.2, opacity: 0.45, arrow: dir !== "both", curvature: 0.25 });
    });
    // and each room-sense links to its global sense hub, so multiple expanded rooms
    // interconnect through the senses they share.
    SENSES.forEach((s) => {
      addLink({ source: `score:${node.label}:${s}`, target: `sense:${s}`, kind: "score-link", sense: s,
        color: SC[s], width: 0.8, opacity: 0.35, curvature: 0.3 });
    });
    // adjacent rooms (the doors that bleed)
    (ctx.gd.edges || []).forEach((e) => {
      if (e.source !== r.roomId && e.target !== r.roomId) return;
      const otherId = e.source === r.roomId ? e.target : e.source;
      const nn = ctx.idToName[otherId];
      if (!nn) return;
      const nr = ctx.byName[nn];
      addNode({ id: `room:${nn}`, kind: "room", label: nn, group: nr ? worstSense(nr) : node.group,
        color: "rgba(228,230,236,0.92)", val: 6 });
      const conf = e.transmissive_conflicts || [];
      addLink({ source: `room:${node.label}`, target: `room:${nn}`, kind: "adjacency",
        mech: `door: ${e.door_name || "—"}${conf.length ? " · bleeds " + conf.join(", ") : ""}`,
        color: conf.length ? SC[conf[0]] : `${FG}0.3)`, width: conf.length ? 1.8 : 0.8,
        opacity: 0.55, arrow: !!conf.length, curvature: 0.22 });
    });
  } else if (node.kind === "sense") {
    const s = node.sense;
    ctx.rooms.forEach((r) => {
      const v = r.comfortScores?.[s] ?? 1;
      if (v >= ctx.thr(s)) return;
      addNode({ id: `room:${r.roomName}`, kind: "room", label: r.roomName, group: s,
        color: "rgba(228,230,236,0.92)", val: 6 });
      addLink({ source: `room:${r.roomName}`, target: `sense:${s}`, kind: "exhibits", sense: s, sign: "-",
        color: SC[s], width: 1 + (ctx.thr(s) - v) * 4, opacity: 0.5, arrow: true, curvature: 0.3 });
    });
    LEVER_SENSE.filter((l) => l[1] === s).forEach(([lv, , sign]) => {
      addNode({ id: `lever:${lv}`, kind: "lever", label: lv, group: s, color: "rgba(26,26,30,0.92)", val: 1.5 });
      addLink({ source: `lever:${lv}`, target: `sense:${s}`, kind: "lever", sign,
        color: `${FG}0.45)`, width: 1, opacity: 0.45, arrow: true, curvature: 0.15 });
    });
    SENSE_SENSE.filter(([a, b]) => a === s || b === s).forEach(([a, b, dir, sign]) => {
      addLink({ source: `sense:${a}`, target: `sense:${b}`, kind: "coupling", sign,
        color: SC[a], width: 1.6, opacity: 0.6, arrow: dir !== "both", curvature: 0.3 });
    });
  } else if (node.kind === "lever") {
    LEVER_SENSE.filter((l) => l[0] === node.label).forEach(([lv, s, sign]) => {
      addLink({ source: `lever:${node.label}`, target: `sense:${s}`, kind: "lever", sign,
        color: SC[s], width: 1.2, opacity: 0.55, arrow: true, curvature: 0.15 });
    });
  }
  return { nodes, links };
}
