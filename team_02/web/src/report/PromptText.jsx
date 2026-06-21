import { SC, SENSES } from "../lib/constants.js";

// Exact mirror of imaging/prompt.py _SENSE_FRAGMENTS [low (<0.45), high (>0.70)].
// Used to locate each voiced sense's words inside the prompt so hovering a petal
// or chip can highlight the slice of language that sense produced.
export const FRAG = {
  thermal:   ["a cool, slightly cold feel with bluish daylight", "a warm, cosy feel with golden light"],
  visual:    ["dim, harsh and visually cluttered with uneven lighting", "bright, airy and visually calm with balanced natural light"],
  acoustic:  ["hard reflective surfaces — bare concrete, glass and tile — that look acoustically live", "soft sound-absorbing textiles, rugs and drapes"],
  spatial:   ["cramped and tight with a low ceiling", "open, spacious and generous in volume"],
  olfactory: ["stuffy and closed with stale air", "fresh and well-ventilated, with a few plants"],
  tactile:   ["cold, hard, unwelcoming materials", "warm natural materials like wood and wool"],
};

// `voiced` mirrors imaging/prompt.py: only a sense scored clearly low (<0.45) or
// clearly high (>0.70) earns a fragment in the prompt — so a room's *weak* senses
// set the mood. Surface exactly those to make the score→prompt link legible.
export const voicedTier = (v) => (v == null ? null : v < 0.45 ? "low" : v > 0.70 ? "high" : null);
export const voicedFromScores = (scores = {}) =>
  SENSES.map((s) => [s, voicedTier(scores[s])]).filter(([, t]) => t);

/*
 * PromptText — renders an image prompt with each voiced sense's exact fragment
 * wrapped so hovering a petal/chip lights up the words that sense produced. Shared
 * by the per-room card and the before/after banner so there's one prompt idiom.
 */
export default function PromptText({ prompt = "", voiced = [], hoverSense }) {
  if (!prompt || !voiced.length) return <>{prompt}</>;
  const marks = voiced
    .map(([s, t]) => ({ s, text: FRAG[s][t === "low" ? 0 : 1] }))
    .filter((m) => prompt.includes(m.text))
    .sort((a, b) => prompt.indexOf(a.text) - prompt.indexOf(b.text));
  if (!marks.length) return <>{prompt}</>;
  const out = [];
  let cursor = 0;
  marks.forEach((m, i) => {
    const idx = prompt.indexOf(m.text, cursor);
    if (idx < 0) return;
    if (idx > cursor) out.push(prompt.slice(cursor, idx));
    out.push(
      <span key={i}
        className={"rr-frag rr-prompt-voiced" + (hoverSense === m.s ? " rr-frag-hi" : "")}
        style={hoverSense === m.s ? { color: SC[m.s] } : undefined}>
        {m.text}
      </span>
    );
    cursor = idx + m.text.length;
  });
  if (cursor < prompt.length) out.push(prompt.slice(cursor));
  return <>{out}</>;
}
