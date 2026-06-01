// ── Sense encoding: the single source of truth ──────────────────────────────
//
// Every visual fact about a sense (its hue, glyph, design baseline) is authored
// HERE, once, as one ordered registry. The rest of the app derives from it:
//   - JS reads SC / SI / BASELINES / SENSES as plain lookups (below).
//   - CSS gets the hues + intensity + status injected onto :root at startup by
//     hydrateCssTokens() in lib/tokens.js, so `var(--thermal)` etc. resolve.
//
// Why JS is the source (not CSS): only JS needs these as literal values (SVG
// `fill`, inline opacity, Framer). CSS only ever needs them via var(), which we
// can hand it. Authoring in one runtime and deriving the other removes the old
// "keep the two in sync" hazard — there is now nothing to keep in sync.
//
// To add or retune a sense, edit ONE row.

export const SENSE_REGISTRY = [
  { key: "thermal",   hue: "#E8836A", glyph: "△", baseline: 0.70 },
  { key: "visual",    hue: "#D4B96A", glyph: "○", baseline: 0.60 },
  { key: "acoustic",  hue: "#9B8FD4", glyph: "∿", baseline: 0.65 },
  { key: "spatial",   hue: "#6AB8C8", glyph: "□", baseline: 0.50 },
  { key: "olfactory", hue: "#8BB88A", glyph: "≈", baseline: 0.40 },
  { key: "tactile",   hue: "#C4A882", glyph: "∶", baseline: 0.35 },
];

// Canonical order — every iteration over senses uses this.
export const SENSES = SENSE_REGISTRY.map((s) => s.key);

// Keyed lookups derived from the registry (was: hand-maintained parallel maps).
export const SC = Object.fromEntries(SENSE_REGISTRY.map((s) => [s.key, s.hue]));
export const SI = Object.fromEntries(SENSE_REGISTRY.map((s) => [s.key, s.glyph]));
export const BASELINES = Object.fromEntries(SENSE_REGISTRY.map((s) => [s.key, s.baseline]));

// ── Status palette — distinct from the six sense hues (for score health only) ──
export const STATUS = { pass: "#3FB97A", warn: "#E0A92E", fail: "#E0524A" };

// One source of truth for score → status color.
export function scoreColor(score) {
  const s = typeof score === "number" ? score : 0;
  return s < 0.5 ? STATUS.fail : s < 0.65 ? STATUS.warn : STATUS.pass;
}

// ── Intensity / health ladder ────────────────────────────────────────────────
// Principle: hue = sense, intensity = health. A sense always owns its hue;
// comfort reads as how vivid it is (opacity), not a red→green hue shift.
export const INTENSITY = [0.10, 0.24, 0.42, 0.66, 0.92];

// Map a 0..1 score to one of the five rungs.
export function scoreOpacity(score) {
  const s = typeof score === "number" ? score : 0;
  if (s < 0.40) return INTENSITY[0];
  if (s < 0.50) return INTENSITY[1];
  if (s < 0.65) return INTENSITY[2];
  if (s < 0.80) return INTENSITY[3];
  return INTENSITY[4];
}
