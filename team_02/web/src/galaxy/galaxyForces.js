// Forces + geometry helpers for the Relationship Galaxy. Hand-written so we add
// no dependency (d3-force-3d is not imported); nodes already carry x/y/z + vx/vy/vz.
import { Vector3 } from "three";
import { SENSES } from "../lib/constants.js";

// Six fixed community anchors spread on a sphere (golden-angle), keyed by sense.
// Every node's `group` resolves to one of these, so the six sense communities
// pull apart and fibers run *between* clusters instead of tangling in the centre.
const R = 120;
export const SENSE_ANCHORS = (() => {
  const out = {};
  const n = SENSES.length;
  const ga = Math.PI * (3 - Math.sqrt(5));
  SENSES.forEach((s, i) => {
    const y = n > 1 ? 1 - (i / (n - 1)) * 2 : 0;     // 1 → -1
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = ga * i;
    out[s] = { x: Math.cos(th) * r * R, y: y * R, z: Math.sin(th) * r * R };
  });
  return out;
})();

// d3 cluster force: nudge each node toward its group's anchor each tick.
export function clusterForce({ strength = 0.14, getGroup, anchors }) {
  let nodes = [];
  const force = (alpha) => {
    const k = strength * alpha;
    for (const nd of nodes) {
      const a = anchors[getGroup(nd)];
      if (!a) continue;
      nd.vx += (a.x - nd.x) * k;
      nd.vy += (a.y - nd.y) * k;
      nd.vz += (a.z - nd.z) * k;
    }
  };
  force.initialize = (n) => { nodes = n; };
  return force;
}

// Settled mean position per group — the live "waist" the bundled fibers route
// through. Writes into `out` (a ref object) and returns it.
export function recomputeCentroids(nodes, out) {
  const acc = {};
  for (const n of nodes) {
    const g = n.group;
    if (!g) continue;
    const a = acc[g] || (acc[g] = { x: 0, y: 0, z: 0, c: 0 });
    a.x += n.x || 0; a.y += n.y || 0; a.z += n.z || 0; a.c++;
  }
  for (const g in acc) {
    const a = acc[g];
    out[g] = { x: a.x / a.c, y: a.y / a.c, z: a.z / a.c };
  }
  return out;
}

// Quadratic-bezier control point for a link. Two effects combine:
//  1. a perpendicular BOW so every fiber arcs delicately (curveRot fans parallels);
//  2. a pull toward the shared community WAIST so many links between the same two
//     clusters converge into a bundle (the DTI-tractography read).
const _up = new Vector3(0, 1, 0);
const _altUp = new Vector3(1, 0, 0);
export function bundleControlPoint(link, s, e, centroids) {
  const mid = new Vector3((s.x + e.x) / 2, (s.y + e.y) / 2, (s.z + e.z) / 2);
  const dir = new Vector3().subVectors(e, s);
  const len = dir.length() || 1;
  dir.multiplyScalar(1 / len);
  const perp = new Vector3().crossVectors(dir, Math.abs(dir.y) < 0.9 ? _up : _altUp).normalize();
  perp.applyAxisAngle(dir, link.curveRot || 0);           // fan parallel fibers into a ribbon
  const ctrl = mid.clone().addScaledVector(perp, len * (link.curvature ?? 0.2) * 1.3);
  const ga = centroids[link.source?.group];
  const gb = centroids[link.target?.group];
  if (ga && gb) {
    const waist = new Vector3((ga.x + gb.x) / 2, (ga.y + gb.y) / 2, (ga.z + gb.z) / 2);
    ctrl.lerp(waist, 0.32);                                // bundle toward the cluster waist
  }
  return ctrl;
}

// k control points fanned around the base control point — render a connection as a
// BUNDLE of thin sub-fibers (the tractography read: many fibers, dense where they
// converge, splayed where they fan).
export function bundleControlPoints(link, s, e, centroids, k = 1) {
  const base = bundleControlPoint(link, s, e, centroids);
  if (k <= 1) return [base];
  const dir = new Vector3().subVectors(e, s);
  const len = dir.length() || 1;
  dir.multiplyScalar(1 / len);
  const perp = new Vector3().crossVectors(dir, Math.abs(dir.y) < 0.9 ? _up : _altUp).normalize();
  perp.applyAxisAngle(dir, (link.curveRot || 0) + Math.PI / 2);   // splay sideways from the bow
  const spread = len * 0.12;
  const out = [];
  for (let i = 0; i < k; i++) {
    const t = (i - (k - 1) / 2) / (k - 1);
    out.push(base.clone().addScaledVector(perp, t * spread));
  }
  return out;
}
