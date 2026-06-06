// ── CSS bridge ───────────────────────────────────────────────────────────────
// The sense encoding is authored in JS (lib/senses.js). This module injects the
// values the stylesheet needs as `var(--…)` onto :root, so the ~1,100 lines of
// ported CSS keep working unchanged while JS stays the single source of truth.
//
// Call hydrateCssTokens() once, before first paint (see main.jsx). The app is
// fully client-rendered, so nothing paints before this runs — no FOUC.

import { SENSE_REGISTRY, STATUS, INTENSITY } from "./senses.js";

export function hydrateCssTokens() {
  if (typeof document === "undefined") return; // SSR / test safety
  const root = document.documentElement.style;

  // sense hues:  --thermal … --tactile
  for (const { key, hue } of SENSE_REGISTRY) root.setProperty(`--${key}`, hue);

  // status palette:  --status-pass / --status-warn / --status-fail
  for (const [name, color] of Object.entries(STATUS)) root.setProperty(`--status-${name}`, color);

  // intensity ladder:  --i-0 … --i-4
  INTENSITY.forEach((v, i) => root.setProperty(`--i-${i}`, String(v)));
}
