// JS mirror of the canonical coupling model (team_02/python/comfort/sense_model.py).
// Keep in sync with the Python source of truth. Used by the focus-card (thresholds,
// provenance) and the sense-coupling graph drawer.
import { SENSES } from "./constants.js";

// Perceptual sense↔sense couplings: [a, b, direction, sign, tier, mechanism]
export const SENSE_SENSE = [
  ["acoustic", "thermal",   "both", "±", "verified", "strongest evidenced cross-modal (bidirectional)"],
  ["acoustic", "visual",    "a->b", "-", "verified", "noise degrades visual comfort"],
  ["visual",   "acoustic",  "a->b", "0", "verified", "light ~no effect on acoustic (asymmetry)"],
  ["thermal",  "olfactory", "both", "+", "verified", "TSV↔ASV association"],
  ["spatial",  "acoustic",  "both", "-", "inferred", "room volume → reverberation (Sabine)"],
  ["tactile",  "acoustic",  "both", "+", "inferred", "surface absorption → reverberation"],
  ["tactile",  "thermal",   "both", "±", "inferred", "material effusivity → contact thermal"],
];

export const TRANSMISSIVE = ["acoustic", "olfactory", "thermal"];

// Provenance encoding (line-style + evocative icon) — one language everywhere.
export const BASIS_ICON = { research: "❝", physics: "⚛", personality: "☺" };
export const BASIS_LABEL = { research: "research", physics: "physics", personality: "personality" };
// SVG strokeDasharray per provenance (solid / dashed / dotted)
export function basisDash(basis) {
  if (basis === "physics") return "5 4";
  if (basis === "personality") return "1.5 4";
  return "none"; // research = solid
}
// CSS border-style per provenance (for HTML chips)
export function basisBorder(basis) {
  if (basis === "physics") return "dashed";
  if (basis === "personality") return "dotted";
  return "solid";
}

// Personal conflict threshold from a comfort weight (mirror threshold_from_weight).
export function thresholdFromWeight(w) {
  const x = typeof w === "number" ? w : 0.5;
  return Math.round((Math.max(0.35, Math.min(0.75, 0.35 + 0.4 * x))) * 100) / 100;
}

// Senses ranked by weight (highest first) — mirror priority_order.
export function priorityOrder(weights) {
  if (!weights) return [...SENSES];
  return [...SENSES].sort((a, b) =>
    (weights[b] ?? 0.5) - (weights[a] ?? 0.5) || SENSES.indexOf(a) - SENSES.indexOf(b));
}
