// The relationship grammar — one visual language for every edge in the instrument
// (per-room sense hub, flow, topology, and later the galaxy).
//
//   VALENCE  (good / bad / trade-off): a glyph + a restrained tint. Hue stays
//            node identity (which sense), so valence must NOT use the sense hues.
//   PROVENANCE (research / physics / personality): line-style — reuse basisDash /
//            basisBorder from senseModel (solid / dashed / dotted).
//   MAGNITUDE: edge width = |delta|.
import { STATUS } from "./senses.js";

export const VALENCE = {
  "+": { glyph: "＋", tint: STATUS.pass, label: "helps" },
  "-": { glyph: "－", tint: STATUS.fail, label: "harms" },
  "±": { glyph: "±",  tint: STATUS.warn, label: "trade-off" },
  "0": { glyph: "·",  tint: "rgba(var(--fg-rgb),0.4)", label: "no effect" },
};

// Sign of a realized cross-modal delta (adjustments carry a numeric delta).
export function signOf(delta) {
  return delta > 0.0001 ? "+" : delta < -0.0001 ? "-" : "0";
}

// Edge width (px) from an adjustment magnitude. Deltas are small (~0.05), so scale up.
export function edgeWidth(delta) {
  return 1 + Math.min(3, Math.abs(delta || 0) * 28);
}
